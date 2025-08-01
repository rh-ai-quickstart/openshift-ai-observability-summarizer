"""
Response Validation and Cleanup for LLM Metric Summaries

Provides validation and cleanup logic to ensure LLM responses contain only
the required content without extra explanations, notes, or repetitive sections.
"""

import re
from typing import Dict, List, Tuple, Optional
from enum import Enum


class ResponseType(Enum):
    """Types of metric analysis responses"""
    OPENSHIFT_ANALYSIS = "openshift_analysis"  # 4-question format
    VLLM_ANALYSIS = "vllm_analysis"  # 5-requirement format
    GENERAL_CHAT = "general_chat"  # Free-form responses


class ResponseValidator:
    """Validates and cleans up LLM responses for metric analysis"""
    
    # Patterns that indicate the model has finished legitimate content
    COMPLETION_INDICATORS = [
        "the final answer",
        "in conclusion",
        "to summarize", 
        "note:",
        "however, since",
        "therefore,",
        "let me know",
        "hope this helps",
        "feel free to ask",
        "please let me know",
        "if you need any further",
        "i have attached",
        "this response meets the guidelines"
    ]
    
    # OpenShift analysis questions (4 questions)
    OPENSHIFT_QUESTIONS = [
        r"what'?s?\s+the\s+current\s+.*?\s+state",
        r"are\s+there\s+.*?performance.*?concerns",
        r"what\s+actions?\s+should\s+be\s+taken",
        r"any\s+optimization\s+recommendations"
    ]
    
    # vLLM analysis requirements (5 requirements)
    VLLM_REQUIREMENTS = [
        r"performance\s+summary",
        r"key\s+metrics?\s+analysis",
        r"trends?\s+and\s+patterns?",
        r"recommendations?",
        r"alerting"
    ]

    @staticmethod
    def detect_response_type(prompt_text: str) -> ResponseType:
        """
        Detect the type of response expected based on the prompt content
        """
        prompt_lower = prompt_text.lower()
        
        # Check for OpenShift 4-question format
        openshift_indicators = ["openshift", "kubernetes", "current state", "performance or reliability concerns"]
        if any(indicator in prompt_lower for indicator in openshift_indicators):
            if "what actions should be taken" in prompt_lower:
                return ResponseType.OPENSHIFT_ANALYSIS
        
        # Check for vLLM 5-requirement format  
        vllm_indicators = ["performance summary", "key metrics analysis", "trends and patterns"]
        if any(indicator in prompt_lower for indicator in vllm_indicators):
            return ResponseType.VLLM_ANALYSIS
            
        return ResponseType.GENERAL_CHAT

    @staticmethod
    def find_completion_point(response: str, response_type: ResponseType) -> int:
        """
        Find where legitimate content ends and extra content begins
        
        Returns:
            int: Character position where to truncate, or -1 if no truncation needed
        """
        response_lower = response.lower()
        
        # Look for completion indicators
        earliest_indicator = len(response)
        for indicator in ResponseValidator.COMPLETION_INDICATORS:
            pos = response_lower.find(indicator.lower())
            if pos != -1:
                earliest_indicator = min(earliest_indicator, pos)
        
        if response_type == ResponseType.OPENSHIFT_ANALYSIS:
            return ResponseValidator._find_openshift_completion(response, earliest_indicator)
        elif response_type == ResponseType.VLLM_ANALYSIS:
            return ResponseValidator._find_vllm_completion(response, earliest_indicator)
        else:
            # For general chat, only remove obvious completion indicators
            return earliest_indicator if earliest_indicator < len(response) else -1

    @staticmethod
    def _find_openshift_completion(response: str, earliest_indicator: int) -> int:
        """Find completion point for OpenShift 4-question responses"""
        
        # Look for all 4 questions being answered
        questions_found = 0
        last_question_end = 0
        
        patterns = ResponseValidator.OPENSHIFT_QUESTIONS
        
        for pattern in patterns:
            # Look for question number or the question text itself
            question_match = re.search(f"[1-4][.)]\s*{pattern}", response, re.IGNORECASE)
            if not question_match:
                # Try without numbering
                question_match = re.search(pattern, response, re.IGNORECASE)
            
            if question_match:
                questions_found += 1
                # Find the end of this question's answer (next question or paragraph break)
                answer_start = question_match.end()
                
                # Look for the next question or significant break
                next_question_pos = len(response)
                for i, next_pattern in enumerate(patterns[questions_found:], questions_found + 1):
                    next_match = re.search(f"[1-4][.)]\s*{next_pattern}", response[answer_start:], re.IGNORECASE)
                    if next_match:
                        next_question_pos = answer_start + next_match.start()
                        break
                
                # The answer ends before the next question or at completion indicators
                answer_end = min(next_question_pos, earliest_indicator)
                last_question_end = max(last_question_end, answer_end)
        
        # If we found all 4 questions, truncate after the last one
        if questions_found >= 4:
            return min(last_question_end, earliest_indicator)
        
        # Otherwise, use completion indicators
        return earliest_indicator if earliest_indicator < len(response) else -1

    @staticmethod
    def _find_vllm_completion(response: str, earliest_indicator: int) -> int:
        """Find completion point for vLLM 5-requirement responses"""
        
        requirements_found = 0
        last_requirement_end = 0
        
        patterns = ResponseValidator.VLLM_REQUIREMENTS
        
        for pattern in patterns:
            # Look for requirement number or the requirement text
            req_match = re.search(f"[1-5][.)]\s*{pattern}", response, re.IGNORECASE)
            if not req_match:
                # Try looking for the pattern in headers
                req_match = re.search(f"##?\s*{pattern}", response, re.IGNORECASE)
            if not req_match:
                # Try without numbering
                req_match = re.search(pattern, response, re.IGNORECASE)
            
            if req_match:
                requirements_found += 1
                # Find the end of this requirement's content
                answer_start = req_match.end()
                
                # Look for the next requirement or significant break
                next_req_pos = len(response)
                for i, next_pattern in enumerate(patterns[requirements_found:], requirements_found + 1):
                    next_match = re.search(f"[1-5][.)]\s*{next_pattern}", response[answer_start:], re.IGNORECASE)
                    if not next_match:
                        next_match = re.search(f"##?\s*{next_pattern}", response[answer_start:], re.IGNORECASE)
                    if next_match:
                        next_req_pos = answer_start + next_match.start()
                        break
                
                # The content ends before the next requirement or at completion indicators
                content_end = min(next_req_pos, earliest_indicator)
                last_requirement_end = max(last_requirement_end, content_end)
        
        # If we found all 5 requirements, truncate after the last one
        if requirements_found >= 5:
            return min(last_requirement_end, earliest_indicator)
        
        # Otherwise, use completion indicators
        return earliest_indicator if earliest_indicator < len(response) else -1

    @staticmethod
    def clean_response(response: str, prompt_text: str = "") -> Dict[str, any]:
        """
        Clean up LLM response by removing unwanted content
        
        Args:
            response: Raw LLM response text
            prompt_text: Original prompt to help determine response type
            
        Returns:
            Dict containing:
                - 'cleaned_response': Cleaned response text
                - 'removed_content': Content that was removed (for debugging)
                - 'validation_info': Information about the validation process
        """
        
        if not response or not response.strip():
            return {
                'cleaned_response': response,
                'removed_content': '',
                'validation_info': {'status': 'empty_response', 'truncated': False}
            }
        
        # Detect response type
        response_type = ResponseValidator.detect_response_type(prompt_text)
        
        # Find where to truncate
        truncate_pos = ResponseValidator.find_completion_point(response, response_type)
        
        if truncate_pos == -1:
            # No truncation needed
            cleaned = ResponseValidator._normalize_whitespace(response)
            return {
                'cleaned_response': cleaned,
                'removed_content': '',
                'validation_info': {
                    'status': 'no_truncation_needed',
                    'response_type': response_type.value,
                    'truncated': False
                }
            }
        
        # Truncate the response
        cleaned_content = response[:truncate_pos].rstrip()
        removed_content = response[truncate_pos:]
        
        # Final cleanup
        cleaned_content = ResponseValidator._normalize_whitespace(cleaned_content)
        cleaned_content = ResponseValidator._remove_incomplete_sentences(cleaned_content)
        
        return {
            'cleaned_response': cleaned_content,
            'removed_content': removed_content,
            'validation_info': {
                'status': 'truncated',
                'response_type': response_type.value,
                'truncated': True,
                'truncate_position': truncate_pos,
                'removed_length': len(removed_content)
            }
        }

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """Normalize whitespace while preserving paragraph structure"""
        # Remove excessive blank lines (more than 2)
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        
        # Remove trailing whitespace from lines
        lines = text.split('\n')
        lines = [line.rstrip() for line in lines]
        
        return '\n'.join(lines).strip()

    @staticmethod
    def _remove_incomplete_sentences(text: str) -> str:
        """Remove sentences that were cut off during truncation"""
        # If the text doesn't end with proper punctuation, remove the last incomplete sentence
        text = text.strip()
        if not text:
            return text
            
        # Check if it ends with proper sentence-ending punctuation
        if text[-1] not in '.!?':
            # Find the last complete sentence
            last_punct = max(
                text.rfind('.'),
                text.rfind('!'), 
                text.rfind('?')
            )
            
            if last_punct > len(text) * 0.8:  # Only if the last punct is near the end
                return text[:last_punct + 1].strip()
        
        return text

    @staticmethod
    def validate_required_content(response: str, response_type: ResponseType) -> Dict[str, any]:
        """
        Validate that the response contains all required elements
        
        Returns:
            Dict with validation results including missing elements
        """
        
        if response_type == ResponseType.OPENSHIFT_ANALYSIS:
            return ResponseValidator._validate_openshift_content(response)
        elif response_type == ResponseType.VLLM_ANALYSIS:
            return ResponseValidator._validate_vllm_content(response)
        else:
            return {'status': 'skipped', 'reason': 'general_chat_not_validated'}

    @staticmethod
    def _validate_openshift_content(response: str) -> Dict[str, any]:
        """Validate OpenShift 4-question response completeness"""
        
        questions_found = []
        patterns = ResponseValidator.OPENSHIFT_QUESTIONS
        
        for i, pattern in enumerate(patterns, 1):
            if re.search(pattern, response, re.IGNORECASE):
                questions_found.append(i)
        
        missing_questions = [i for i in range(1, 5) if i not in questions_found]
        
        return {
            'status': 'complete' if len(questions_found) == 4 else 'incomplete',
            'questions_found': questions_found,
            'missing_questions': missing_questions,
            'completeness_score': len(questions_found) / 4.0
        }

    @staticmethod
    def _validate_vllm_content(response: str) -> Dict[str, any]:
        """Validate vLLM 5-requirement response completeness"""
        
        requirements_found = []
        patterns = ResponseValidator.VLLM_REQUIREMENTS
        
        for i, pattern in enumerate(patterns, 1):
            if re.search(pattern, response, re.IGNORECASE):
                requirements_found.append(i)
        
        missing_requirements = [i for i in range(1, 6) if i not in requirements_found]
        
        return {
            'status': 'complete' if len(requirements_found) == 5 else 'incomplete', 
            'requirements_found': requirements_found,
            'missing_requirements': missing_requirements,
            'completeness_score': len(requirements_found) / 5.0
        }

    @staticmethod 
    def remove_repetitive_patterns(text: str) -> str:
        """
        Remove specific repetitive patterns commonly seen in Llama-3.2-3B-instruct
        """
        # Remove repeated "Note:" sections
        lines = text.split('\n')
        cleaned_lines = []
        seen_notes = set()
        
        for line in lines:
            line_stripped = line.strip()
            
            # Check for repetitive note patterns
            if line_stripped.startswith("Note:") or "However, since" in line_stripped:
                # Normalize for comparison
                normalized = re.sub(r'\s+', ' ', line_stripped.lower())
                if normalized in seen_notes:
                    continue  # Skip this repetitive line
                seen_notes.add(normalized)
            
            cleaned_lines.append(line)
        
        # Join back and remove obvious repetitive sentences
        cleaned_text = '\n'.join(cleaned_lines)
        
        # Remove repeated sentences (exact matches)
        sentences = cleaned_text.split('.')
        unique_sentences = []
        seen_sentences = set()
        
        for sentence in sentences:
            normalized_sentence = re.sub(r'\s+', ' ', sentence.strip().lower())
            if normalized_sentence and normalized_sentence not in seen_sentences:
                unique_sentences.append(sentence)
                seen_sentences.add(normalized_sentence)
        
        return '.'.join(unique_sentences)