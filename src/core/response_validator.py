"""
Response Validation and Cleanup for LLM Metric Summaries

This module provides comprehensive validation and cleanup logic to ensure LLM responses 
contain only the required content without extra explanations, notes, or repetitive sections.

KEY VALIDATION STRATEGIES:
=========================

1. **Paragraph-based Analysis**: Splits responses into logical paragraphs and validates
   the expected structure based on response type (OpenShift 4-question vs vLLM 5-requirement).

2. **Content Truncation**: Removes extra content that appears after the required sections,
   such as "Note:", "Feel free to ask", "Hope this helps", etc.

3. **Bullet Point Validation**: For vLLM responses, ensures the Alerting section contains
   only bullet points (max 3) and properly handles formatted bullet content.

4. **Sentence Completion**: Removes incomplete sentences that were cut off during truncation
   while preserving valid bullet points that don't end with punctuation.

5. **Whitespace Normalization**: Cleans up excessive blank lines and trailing whitespace
   while preserving paragraph structure.

RESPONSE TYPES SUPPORTED:
========================

- **OPENSHIFT_ANALYSIS**: 4-question format for OpenShift metrics analysis
- **VLLM_ANALYSIS**: 5-requirement format for vLLM performance analysis  
- **GENERAL_CHAT**: Free-form responses without structural constraints

VALIDATION FLOW:
===============

1. Parse response into paragraphs
2. Identify substantive content paragraphs (filter out headers/questions)
3. Apply type-specific validation rules
4. Find optimal truncation point
5. Clean up whitespace and incomplete sentences
6. Return cleaned response with validation metadata

This approach ensures consistent, clean responses while preserving all required content.
"""

import re
import logging
from typing import Dict, List, Tuple, Optional
from enum import Enum
from common.pylogger import get_python_logger

# Initialize structured logger once - other modules should use logging.getLogger(__name__)
get_python_logger()

logger = logging.getLogger(__name__)


class ResponseType(Enum):
    """Types of metric analysis responses"""
    OPENSHIFT_ANALYSIS = "openshift_analysis"  # 4-question format
    VLLM_ANALYSIS = "vllm_analysis"  # 5-requirement format
    GENERAL_CHAT = "general_chat"  # Free-form responses


class ResponseValidator:
    """
    Validates and cleans up LLM responses for metric analysis.
    
    This class implements a sophisticated validation system that handles different
    response formats while removing unwanted extra content that LLMs often add.
    """
    

    
    # Regex patterns for the 4 required OpenShift analysis questions.
    # These patterns are flexible to handle variations in wording and formatting.
    OPENSHIFT_QUESTIONS = [
        r"what'?s?\s+the\s+current\s+.*?state",     # Q1: Current state
        r"are\s+there\s+.*?performance.*?concerns",     # Q2: Performance concerns
        r"what\s+actions?\s+should\s+be\s+taken",       # Q3: Recommended actions
        r"any\s+optimization\s+recommendations"        # Q4: Optimization recommendations
    ]
    
    # Regex patterns for the 5 required vLLM analysis requirements.
    # These patterns match section headers and ensure all requirements are covered.
    VLLM_REQUIREMENTS = [
        r"performance\s+summary",     # Req 1: Overall performance summary
        r"key\s+metrics?\s+analysis", # Req 2: Key metrics analysis
        r"trends?\s+and\s+patterns?", # Req 3: Trends and patterns
        r"recommendations?",          # Req 4: Recommendations
        r"alerting"                   # Req 5: Alerting (special bullet point section)
    ]

    @staticmethod
    def find_completion_point(response: str, response_type: ResponseType) -> int:
        """
        Find where legitimate content ends using sophisticated paragraph-based detection.
        
        This is the main entry point for response validation. It uses a model-agnostic 
        approach that analyzes the logical structure of responses rather than relying 
        on specific keywords or patterns that might vary between LLM models.
        
        APPROACH:
        ---------
        1. Split response into logical paragraphs using multiple separators
        2. Filter out empty paragraphs and headers-only content  
        3. Apply response-type-specific validation rules
        4. Return optimal truncation point that preserves all required content
        
        HANDLES:
        --------
        - Questions/requirements included within answer paragraphs
        - Variable line breaks between sections
        - Single paragraph answers with embedded bullet points
        - Type-specific content constraints (4 questions vs 5 requirements)
        - Bullet point validation for vLLM Alerting sections
        
        Args:
            response: Raw LLM response text to validate
            response_type: Expected response format (OPENSHIFT/VLLM/GENERAL_CHAT)
        
        Returns:
            int: Character position where to truncate, or -1 if no truncation needed
        """
        if not response or not response.strip():
            return -1
            
        # Split into paragraphs using multiple separator patterns:
        # - Double newlines (standard paragraph breaks)
        # - Lines of dashes (horizontal rules) 
        # - Lines of equal signs (section separators)
        paragraphs = re.split(r'\n\s*\n|\n\s*-{3,}|\n\s*={3,}', response.strip())
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        if not paragraphs:
            return -1
            
        # Delegate to response-type-specific validation logic
        if response_type == ResponseType.OPENSHIFT_ANALYSIS:
            return ResponseValidator._find_openshift_completion_paragraphs(response, paragraphs)
        elif response_type == ResponseType.VLLM_ANALYSIS:
            return ResponseValidator._find_vllm_completion_paragraphs(response, paragraphs)
        else:  # GENERAL_CHAT
            return ResponseValidator._find_general_completion_paragraphs(response, paragraphs)

    @staticmethod
    def _find_openshift_completion_paragraphs(response: str, paragraphs: List[str]) -> int:
        """
        Find completion point for OpenShift 4-question responses using paragraph analysis.
        
        Expected structure: 4 paragraphs for 4 questions, each may include question + answer
        """
        # OpenShift should have exactly 4 substantive paragraphs
        substantive_paragraphs = []
        current_pos = 0
        
        for para in paragraphs:
            # Find this paragraph's position in original response
            para_start = response.find(para, current_pos)
            if para_start == -1:
                continue
                
            para_end = para_start + len(para)
            current_pos = para_end
            
            # Check if this paragraph contains substantial content (not just a question)
            if len(para.strip()) > 20 and not ResponseValidator._is_just_question(para):
                substantive_paragraphs.append((para, para_end))
        
        # For OpenShift: be more flexible with paragraph count
        # Only truncate if we have extra content beyond what looks like a complete response
        if len(substantive_paragraphs) >= 4:
            # If we have 4+ paragraphs, check if there's extra content after the 4th
            # that looks like repetitive or explanatory content
            fourth_para_end = substantive_paragraphs[3][1]
            remaining_content = response[fourth_para_end:].strip()
            
            # If remaining content contains repetitive patterns, truncate
            if remaining_content and any(pattern in remaining_content.lower() for pattern in 
                ['note:', 'however, since', 'therefore,', 'the answer to question']):
                return fourth_para_end
            else:
                # No repetitive content found, don't truncate
                return -1
        elif len(substantive_paragraphs) > 0:
            # For incomplete responses, check for repetitive content within the paragraph
            last_para = substantive_paragraphs[-1][0]
            last_para_end = substantive_paragraphs[-1][1]
            
            # Check if the paragraph itself contains repetitive patterns
            if any(pattern in last_para.lower() for pattern in 
                ['note:', 'however, since', 'therefore,', 'the answer to question']):
                # Find where the repetitive content starts
                for pattern in ['note:', 'however, since', 'therefore,', 'the answer to question']:
                    pattern_pos = last_para.lower().find(pattern)
                    if pattern_pos != -1:
                        # Calculate the position in the original response
                        para_start = response.find(last_para, last_para_end - len(last_para))
                        if para_start != -1:
                            return para_start + pattern_pos
            
            # Check remaining content after the paragraph
            remaining_content = response[last_para_end:].strip()
            if remaining_content and any(pattern in remaining_content.lower() for pattern in 
                ['note:', 'however, since', 'therefore,', 'the answer to question']):
                return last_para_end
        
        return -1

    @staticmethod  
    def _find_vllm_completion_paragraphs(response: str, paragraphs: List[str]) -> int:
        """
        Find completion point for vLLM 5-requirement responses using paragraph analysis.
        
        This handles the complex vLLM response format which requires exactly 5 sections:
        1. Performance Summary
        2. Key Metrics Analysis  
        3. Trends and Patterns
        4. Recommendations
        5. Alerting (special bullet-point-only section with max 3 bullets)
        
        SPECIAL ALERTING VALIDATION:
        ---------------------------
        The Alerting section has strict requirements:
        - Must contain ONLY bullet points (no other text)
        - Maximum of 3 bullet points allowed
        - Section headers like "**5. Attentions**" must be excluded from bullet count
        - If validation fails, the entire section is removed to prevent malformed output
        
        This validation was recently fixed to properly handle formatted headers like:
        "**5. Attentions**", "**Alerting**", "5. Alerting", etc.
        
        Args:
            response: Full response text
            paragraphs: Pre-split paragraph list
            
        Returns:
            int: Character position for optimal truncation point
        """
        substantive_paragraphs = []
        current_pos = 0
        alerting_para = None
        
        # Analyze each paragraph to find substantive content
        for para in paragraphs:
            # Track position within original response for accurate truncation
            para_start = response.find(para, current_pos)
            if para_start == -1:
                continue
                
            para_end = para_start + len(para)
            current_pos = para_end
            
            # Filter out requirement headers and very short content
            if len(para.strip()) > 20 and not ResponseValidator._is_just_requirement(para):
                substantive_paragraphs.append((para, para_end))
                
                # Detect alerting section by multiple possible names
                if re.search(r'\b(alert|alerting|alerts|attention|attentions)\b', para, re.IGNORECASE):
                    alerting_para = para
        
        # vLLM responses should have exactly 5 substantive sections
        if len(substantive_paragraphs) >= 5:
            
            # CRITICAL: Special validation for Alerting section (requirement 5)
            if alerting_para:
                is_valid_format = ResponseValidator._validate_alerting_format(alerting_para)
                if not is_valid_format:
                    # If alerting format is invalid (too many bullets, non-bullet content, etc.),
                    # truncate BEFORE the alerting section to prevent malformed output
                    for i, (para, end_pos) in enumerate(substantive_paragraphs):
                        if alerting_para in para:
                            if i > 0:
                                return substantive_paragraphs[i-1][1]
                            break
            
            # For valid Alerting sections, find precise end point respecting bullet limits
            if alerting_para:
                alerting_end = ResponseValidator._find_alerting_end_point(response, alerting_para)
                if alerting_end != -1:
                    return alerting_end
            
            # Default: return end of 5th paragraph (or last if fewer than 5)
            return substantive_paragraphs[4][1] if len(substantive_paragraphs) >= 5 else substantive_paragraphs[-1][1]
        elif len(substantive_paragraphs) > 0:
            # Incomplete response: return end of last substantive paragraph
            return substantive_paragraphs[-1][1]
        
        return -1

    @staticmethod
    def _find_general_completion_paragraphs(response: str, paragraphs: List[str]) -> int:
        """
        Find completion point for general chat responses using paragraph analysis.
        
        Expected structure: Single paragraph answer
        """

        if len(paragraphs) >= 1:
            # For general chat, typically expect one main paragraph
            # Find the end of the first substantive paragraph
            for para in paragraphs:
                if len(para.strip()) > 20:
                    para_end = response.find(para) + len(para)
                    return para_end
        
        return -1

    @staticmethod
    def _is_just_question(text: str) -> bool:
        """Check if text is just a question without substantial answer content"""
        text = text.strip()
        if len(text) < 50:  # Very short, likely just a question
            return True
        if text.count('?') > 0 and len(text.replace('?', '').strip()) < 30:
            return True
        return False

    @staticmethod
    def _is_just_requirement(text: str) -> bool:
        """Check if text is just a requirement header without substantial content"""
        text = text.strip()
        if len(text) < 50:  # Very short, likely just a requirement
            return True
        # Check for requirement-like patterns
        requirement_patterns = [
            r'^\d+\.\s*[A-Z][a-z\s]+:?\s*$',  # "1. Performance Summary:"
            r'^[A-Z][a-z\s]+:?\s*$',          # "Performance Summary:"
        ]
        for pattern in requirement_patterns:
            if re.match(pattern, text):
                return True
        return False

    @staticmethod
    def _validate_alerting_format(alerting_text: str) -> bool:
        """
        Validate that alerting section meets strict vLLM_ANALYSIS requirements.
        
        REQUIREMENTS:
        ------------
        1. Contains ONLY bullet points (no paragraphs, explanations, or other text)
        2. Maximum of 3 bullet points allowed
        3. Section headers must be excluded from bullet point count
        
        SUPPORTED HEADER FORMATS (excluded from validation):
        --------------------------------------------------
        - "**5. Attentions**" (with markdown formatting)
        - "**Alerting**" (section header only)
        - "5. Alerting" (numbered header)
        - "Alerting", "Attention", "Attentions" (plain headers)
        
        SUPPORTED BULLET FORMATS (counted as bullet points):
        ---------------------------------------------------
        - "1. High latency detected"
        - "• Memory usage critical" 
        - "- Performance degraded"
        - "* Alert condition met"
        
        RECENT FIX:
        ----------
        Previously, headers like "**5. Attentions**" were incorrectly counted as bullet 
        points due to the "5." pattern. The regex was fixed to properly exclude these 
        headers while preserving actual bullet point validation.
        
        Args:
            alerting_text: The alerting section text to validate
            
        Returns:
            bool: True if format is valid, False if it violates requirements
        """
        lines = alerting_text.split('\n')
        content_lines = []
        bullet_points = []
        
        for line in lines:
            line = line.strip()
            
            # CRITICAL: Skip section headers to avoid false bullet point detection
            # This regex handles: "**5. Attentions**", "**Alerting**", "5. Alerting", etc.
            header_pattern = r'^(\*\*)?[0-9]*\.?\s*(alerting|attention|attentions)(\*\*)?\s*$'
            if line and not re.match(header_pattern, line, re.IGNORECASE):
                content_lines.append(line)
                
                # Check if this line is a bullet point (starts with bullet symbols/numbers)
                if re.match(r'^[-*•0-9]+\.?\s+', line):
                    bullet_points.append(line)
        
        # Empty alerting sections are acceptable
        if not content_lines:
            return True
        
        # REQUIREMENT 1: Maximum 3 bullet points
        if len(bullet_points) > 3:
            return False
            
        # REQUIREMENT 2: ALL content must be bullet points (no other text allowed)
        for line in content_lines:
            line = line.strip()
            if line and not re.match(r'^[-*•0-9]+\.?\s+', line):
                return False  # Found non-bullet content (paragraphs, explanations, etc.)
                
        return True

    @staticmethod
    def _find_alerting_end_point(response: str, alerting_para: str) -> int:
        """
        Find the precise end point of the Alerting/Attentions section.
        
        This function implements the requirement: "For each bullet point for alerting, 
        the end should be either a line break, or the end of the string"
        
        PURPOSE:
        -------
        - Ensures exactly 3 bullet points are included (no more, no less)
        - Calculates precise character position for truncation
        - Handles various bullet point formats consistently
        - Excludes section headers from bullet point counting
        
        ALGORITHM:
        ---------
        1. Locate the alerting paragraph within the full response
        2. Process each line within the alerting section
        3. Skip headers and empty lines
        4. Count valid bullet points up to the limit of 3
        5. Return character position at end of the 3rd bullet point
        
        EDGE CASES HANDLED:
        ------------------
        - Mixed header formats: "**5. Attentions**", "Alerting:", etc.
        - Variable bullet symbols: "-", "*", "•", "1.", "2.", etc.
        - Content after 3rd bullet is automatically truncated
        - Non-bullet content stops processing immediately
        
        Args:
            response: Full response text for position calculation
            alerting_para: The specific alerting paragraph to process
            
        Returns:
            int: Character position where alerting section should end
        """
        # Locate alerting paragraph within the full response for accurate positioning
        alerting_start = response.find(alerting_para)
        if alerting_start == -1:
            return -1
            
        # Process each line in the alerting section
        lines = alerting_para.split('\n')
        bullet_count = 0
        current_pos = 0  # Tracks position within the alerting_para text
        last_bullet_end_pos = alerting_start
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # Skip empty lines and section headers (same logic as validation)
            header_pattern = r'^(\*\*)?[0-9]*\.?\s*(alerting|attention|attentions)(\*\*)?\s*$'
            if not line_stripped or re.match(header_pattern, line_stripped, re.IGNORECASE):
                current_pos += len(line) + 1  # +1 accounts for newline character
                continue
            
            # Process bullet point lines
            if re.match(r'^[-*•0-9]+\.?\s+', line_stripped):
                bullet_count += 1
                
                # Calculate absolute position of this line's end in the full response
                line_end_pos = alerting_start + current_pos + len(line)
                last_bullet_end_pos = line_end_pos
                
                # Update position tracker for next iteration
                current_pos += len(line) + 1  # +1 for newline
                
                # ENFORCE 3 BULLET LIMIT: Stop after processing 3rd bullet point
                if bullet_count >= 3:
                    break
            else:
                # Found non-bullet content after bullets - stop processing
                # This prevents including explanatory text after bullet points
                break
                
        return last_bullet_end_pos

    @staticmethod  
    def clean_response(response: str, response_type: ResponseType, prompt_text: str = "") -> Dict[str, any]:
        """
        Main entry point for LLM response validation and cleanup.
        
        This function orchestrates the complete validation pipeline:
        1. Paragraph-based structural analysis
        2. Type-specific validation rules
        3. Intelligent truncation point detection
        4. Whitespace normalization
        5. Incomplete sentence cleanup (with bullet point preservation)
        
        VALIDATION PIPELINE:
        ===================
        
        INPUT: Raw LLM response (may contain extra content, formatting issues)
           ↓
        STEP 1: find_completion_point() - Analyze structure, find optimal truncation point
           ↓
        STEP 2: Truncate at identified position (preserves all required content)
           ↓  
        STEP 3: _normalize_whitespace() - Clean up excessive blank lines, trailing spaces
           ↓
        STEP 4: _remove_incomplete_sentences() - Remove truncated sentences, preserve bullets
           ↓
        OUTPUT: Clean response with validation metadata
        
        HANDLES COMPLEX CASES:
        =====================
        - vLLM Alerting sections with strict bullet point requirements
        - OpenShift 4-question responses with variable formatting
        - Incomplete sentences from mid-word truncation
        - Formatted headers that look like bullet points
        - Extra conversational content ("Hope this helps", etc.)
        
        Args:
            response: Raw LLM response text (potentially messy)
            response_type: Expected format (OPENSHIFT_ANALYSIS/VLLM_ANALYSIS/GENERAL_CHAT)
            prompt_text: Original prompt (optional, used for debugging context)
            
        Returns:
            Dict containing:
                - 'cleaned_response': Fully validated and cleaned response text
                - 'removed_content': Content that was truncated (for debugging/monitoring)
                - 'validation_info': Detailed metadata about the validation process
        """
        
        # Handle empty or whitespace-only responses
        if not response or not response.strip():
            return {
                'cleaned_response': response,
                'removed_content': '',
                'validation_info': {'status': 'empty_response', 'truncated': False}
            }
        
        if prompt_text.lower().find("alerts") != -1:
            return {
                'cleaned_response': response,
                'removed_content': '',
                'validation_info': {'status': 'empty_response', 'truncated': False}
            }
        
        # STEP 1: Analyze response structure and find optimal truncation point
        # This is where the sophisticated paragraph-based validation happens
        truncate_pos = ResponseValidator.find_completion_point(response, response_type)
        
        if truncate_pos == -1:
            # Response is already clean - just normalize whitespace
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
        
        # STEP 2: Truncate at the identified position
        cleaned_content = response[:truncate_pos].rstrip()
        removed_content = response[truncate_pos:]
        
        # STEP 3 & 4: Final cleanup pipeline
        cleaned_content = ResponseValidator._normalize_whitespace(cleaned_content)
        cleaned_content = ResponseValidator._remove_incomplete_sentences(cleaned_content)
        
        # Debugging: Log when content is removed (helps with monitoring/tuning)
        if len(removed_content) > 0:
            max_log_len = 200
            truncated_removed = (removed_content[:max_log_len] + '... [truncated]') if len(removed_content) > max_log_len else removed_content
            truncated_response = (response[:max_log_len] + '... [truncated]') if len(response) > max_log_len else response
            logger.debug("Removed content: %s. Original model response: %s", truncated_removed, truncated_response)
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
        """
        Remove sentences that were cut off during truncation while preserving valid bullet points.
        
        This function handles a critical edge case: truncated responses may end with incomplete
        sentences that need to be removed, but bullet points often don't end with punctuation
        and should be preserved.
        
        LOGIC:
        -----
        1. If text ends with proper punctuation (.!?), it's considered complete - no changes
        2. If text doesn't end with punctuation, check if the last line is a bullet point
        3. If it's a bullet point, preserve it (bullet points don't require punctuation)
        4. If it's not a bullet point, find the last complete sentence and truncate there
        
        RECENT FIX:
        ----------
        Previously, bullet points like "3. High GPU energy consumption" were being
        truncated because they don't end with sentence punctuation. The fix adds
        bullet point detection to preserve these valid content endings.
        
        EXAMPLES:
        --------
        ✅ PRESERVED: "3. High GPU energy consumption" (valid bullet point)
        ✅ PRESERVED: "The system is stable." (ends with punctuation) 
        ❌ REMOVED: "The system is stab" (incomplete sentence)
        
        Args:
            text: Text that may have incomplete sentences from truncation
            
        Returns:
            str: Text with incomplete sentences removed, bullet points preserved
        """
        text = text.strip()
        if not text:
            return text
            
        # If text ends with proper sentence-ending punctuation, it's complete
        if text[-1] not in '.!?':
            # Check if the last line is a bullet point - these don't need sentence punctuation
            lines = text.split('\n')
            last_line = lines[-1].strip() if lines else ""
            
            # BULLET POINT PRESERVATION: Don't remove bullet points that lack punctuation
            # Matches: "1. Item", "• Item", "- Item", "* Item"
            if re.match(r'^[-*•0-9]+\.?\s+.+', last_line):
                return text
            
            # For non-bullet content, find the last complete sentence
            last_punct = max(
                text.rfind('.'),
                text.rfind('!'), 
                text.rfind('?')
            )
            
            # Truncate at the last punctuation mark if found
            if last_punct > 0:
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