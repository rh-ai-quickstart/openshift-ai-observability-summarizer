"""
Usage Examples for Response Validation and Cleanup

Demonstrates how to use the ResponseValidator for cleaning up LLM responses
in OpenShift and vLLM metric analysis scenarios.
"""

from src.core.llm_client import summarize_with_llm, summarize_with_llm_detailed
from src.core.response_validator import ResponseValidator, ResponseType


def example_openshift_analysis():
    """Example of using validation for OpenShift metric analysis"""
    
    # Sample OpenShift prompt (4-question format)
    openshift_prompt = """
    You are an expert in OpenShift platform monitoring. Analyze these GPU metrics:
    
    📊 AVAILABLE METRICS:
    • GPU Temperature (°C): Latest=45.2, Avg=44.8, Trend=stable, normal
    • GPU Power Usage (Watts): Latest=200.5, Avg=195.3, Trend=increasing, normal  
    • GPU Utilization (%): Latest=75.2, Avg=68.4, Trend=stable, normal
    • GPU Memory Usage (GB): Latest=12.4, Avg=11.8, Trend=stable, normal
    
    Instructions:
    1. Answer each of the 4 questions below using only the provided metrics
    2. Stop after you have answered question 4 and do not add explanations or notes
    
    Questions:
    1. What's the current gpu & accelerators state?
    2. Are there performance or reliability concerns?
    3. What actions should be taken?
    4. Any optimization recommendations?
    """
    
    # Example of problematic LLM response (with extra content)
    problematic_response = """
    1. What's the current gpu & accelerators state?
    The GPU & accelerators are in stable condition with temperatures at 45.2°C and utilization at 75.2%.
    
    2. Are there performance or reliability concerns?
    No immediate concerns, though power usage shows increasing trend at 200.5W.
    
    3. What actions should be taken?
    Monitor power consumption trends and consider workload optimization.
    
    4. Any optimization recommendations?
    Consider implementing power management policies for better efficiency.
    
    The final answer is:
    - Current state: Stable operation
    - Concerns: Increasing power usage
    - Actions: Monitor trends
    - Optimization: Power management
    
    Note: This analysis is based on the assumption that the current metrics represent normal operational parameters. 
    However, if you need more detailed analysis, please provide additional context about expected performance baselines.
    Let me know if you need any clarification on these recommendations!
    """
    
    print("=== OpenShift Analysis Example ===")
    print("Raw Response Length:", len(problematic_response))
    
    # Clean the response
    validation_result = ResponseValidator.clean_response(problematic_response, openshift_prompt)
    
    print("\n--- Cleaned Response ---")
    print(validation_result['cleaned_response'])
    
    print(f"\n--- Validation Info ---")
    print(f"Status: {validation_result['validation_info']['status']}")
    print(f"Response Type: {validation_result['validation_info']['response_type']}")
    print(f"Truncated: {validation_result['validation_info']['truncated']}")
    
    if validation_result['removed_content']:
        print(f"\n--- Removed Content ({len(validation_result['removed_content'])} chars) ---")
        print(validation_result['removed_content'][:200] + "..." if len(validation_result['removed_content']) > 200 else validation_result['removed_content'])
    
    # Validate content completeness
    response_type = ResponseValidator.detect_response_type(openshift_prompt)
    content_validation = ResponseValidator.validate_required_content(
        validation_result['cleaned_response'], response_type
    )
    
    print(f"\n--- Content Validation ---")
    print(f"Completeness: {content_validation['status']}")
    print(f"Score: {content_validation['completeness_score']:.1%}")
    print(f"Questions Found: {content_validation['questions_found']}")
    print(f"Missing Questions: {content_validation['missing_questions']}")


def example_vllm_analysis():
    """Example of using validation for vLLM metric analysis"""
    
    # Sample vLLM prompt (5-requirement format)
    vllm_prompt = """
    You are a machine learning model performance analysis expert. Analyze these vLLM metrics:
    
    METRICS DATA:
    === REQUEST LATENCY ===
    Latest value: 0.85s, Average: 0.72s, Min: 0.45s, Max: 1.20s
    
    === THROUGHPUT ===
    Latest value: 125.3 req/s, Average: 118.7 req/s, Min: 95.2s, Max: 142.1s
    
    ANALYSIS REQUIREMENTS:
    1. **Performance Summary**: Overall health and performance status
    2. **Key Metrics Analysis**: Interpret the most important metrics  
    3. **Trends and Patterns**: Identify any concerning trends
    4. **Recommendations**: Actionable suggestions for optimization
    5. **Alerting**: Summarize top 3 issues that are happening and need attention
    
    Stop after you have answered requirement 5 and do not add explanations or notes.
    """
    
    # Example of problematic response with repetitive content
    problematic_response = """
    1. **Performance Summary**: The system shows good overall performance with average latency of 0.72s and throughput of 118.7 req/s.
    
    2. **Key Metrics Analysis**: Request latency is within acceptable bounds, though the maximum of 1.20s indicates occasional spikes.
    
    3. **Trends and Patterns**: Latency shows some variability with spikes, while throughput remains relatively stable.
    
    4. **Recommendations**: Implement request queuing optimization and consider scaling during peak periods.
    
    5. **Alerting**: Top issues: 1) Latency spikes above 1s, 2) Throughput variance, 3) Peak period capacity.
    
    In conclusion, the analysis shows that while the system is performing adequately, there are opportunities for optimization.
    
    Note: These recommendations are based on the current metrics snapshot. For a more comprehensive analysis, historical data would be beneficial.
    However, the current data suggests that the system is operating within normal parameters with room for improvement.
    Therefore, I recommend implementing the suggested optimizations to enhance performance.
    """
    
    print("\n\n=== vLLM Analysis Example ===")
    print("Raw Response Length:", len(problematic_response))
    
    # Clean the response  
    validation_result = ResponseValidator.clean_response(problematic_response, vllm_prompt)
    
    print("\n--- Cleaned Response ---")
    print(validation_result['cleaned_response'])
    
    print(f"\n--- Validation Info ---")
    print(f"Status: {validation_result['validation_info']['status']}")
    print(f"Response Type: {validation_result['validation_info']['response_type']}")
    print(f"Truncated: {validation_result['validation_info']['truncated']}")
    
    if validation_result['removed_content']:
        print(f"\n--- Removed Content ({len(validation_result['removed_content'])} chars) ---")
        print(validation_result['removed_content'])


def example_repetitive_pattern_removal():
    """Example of removing repetitive patterns like the original Llama-3.2-3B issue"""
    
    # The actual repetitive response you showed me
    repetitive_response = """
    4. Any optimization recommendations?
    No optimization recommendations can be made based on the available metrics. The stable state of the gpu & accelerators suggests that no optimization is necessary at this time.
    
    Note: The answer to question 4 is based on the assumption that the stable state of the gpu & accelerators is a result of proper configuration and maintenance. If the stable state is due to other factors, additional analysis may be required.
    However, since the stable state is explicitly indicated by the "stable" labels, the answer to question 4 is based on the assumption that the stable state is a result of proper configuration and maintenance.
    Therefore, no optimization recommendations can be made based on the available metrics.
    Note: The answer to question 4 is based on the assumption that the stable state of the gpu & accelerators is a result of proper configuration and maintenance. If the stable state is due to other factors, additional analysis may be required.
    However, since the stable state is explicitly indicated by the "stable" labels, the answer to question 4 is based on the assumption that the stable state is a result of proper configuration and maintenance.
    Therefore, no optimization recommendations can be made based on the available metrics.
    Note: The answer to question 4 is based on the assumption that the stable state of the gpu & accelerators is a result of proper configuration and maintenance. If the stable state is due to other factors, additional analysis may be required.
    """
    
    print("\n\n=== Repetitive Pattern Removal Example ===")
    print("Original Length:", len(repetitive_response))
    
    # Apply repetitive pattern removal
    cleaned = ResponseValidator.remove_repetitive_patterns(repetitive_response)
    
    print("\n--- After Repetitive Pattern Removal ---")
    print(cleaned)
    print(f"\nReduced from {len(repetitive_response)} to {len(cleaned)} characters")


def example_integration_with_llm():
    """Example of using the enhanced LLM function with validation"""
    
    print("\n\n=== Integration Example ===")
    
    # Mock prompt for demonstration
    sample_prompt = """
    Analyze OpenShift pod metrics:
    
    Questions:
    1. What's the current fleet overview state?
    2. Are there performance or reliability concerns?
    3. What actions should be taken?
    4. Any optimization recommendations?
    """
    
    print("✅ Basic Usage - summarize_with_llm (validation enabled by default):")
    print("   clean_response = summarize_with_llm(prompt, model_id)")
    print("   → Returns clean response, extra content automatically removed")
    
    print("\n✅ Detailed Usage - summarize_with_llm_detailed:")
    print("   result = summarize_with_llm_detailed(prompt, model_id)")
    print("   → Returns: response, raw_response, validation_info, content_validation")
    
    print("\n✅ Disable validation when needed:")
    print("   raw_response = summarize_with_llm(prompt, model_id, enable_validation=False)")
    print("   → Returns unprocessed LLM response")


def example_response_types():
    """Example of response type detection"""
    
    print("\n\n=== Response Type Detection ===")
    
    openshift_prompt = "Analyze OpenShift metrics. What's the current state? Are there concerns?"
    vllm_prompt = "Performance Summary: Analyze vLLM metrics. Key Metrics Analysis needed."
    chat_prompt = "How are things looking with my models today?"
    
    print(f"OpenShift prompt → {ResponseValidator.detect_response_type(openshift_prompt).value}")
    print(f"vLLM prompt → {ResponseValidator.detect_response_type(vllm_prompt).value}")  
    print(f"Chat prompt → {ResponseValidator.detect_response_type(chat_prompt).value}")


def example_validation_monitoring():
    """Example of monitoring validation effectiveness"""
    
    print("\n\n=== Validation Monitoring Example ===")
    
    # Sample monitoring code
    validation_stats = {
        'total_responses': 100,
        'truncated_responses': 15,
        'avg_content_removed': 247,  # characters
        'avg_completeness_score': 0.95,
        'response_types': {
            'openshift_analysis': 45,
            'vllm_analysis': 30,
            'general_chat': 25
        }
    }
    
    print("📊 Validation Effectiveness Metrics:")
    print(f"   Truncation Rate: {validation_stats['truncated_responses']}/{validation_stats['total_responses']} ({validation_stats['truncated_responses']/validation_stats['total_responses']:.1%})")
    print(f"   Avg Content Removed: {validation_stats['avg_content_removed']} characters")
    print(f"   Avg Completeness Score: {validation_stats['avg_completeness_score']:.1%}")
    print(f"   Response Type Distribution:")
    for resp_type, count in validation_stats['response_types'].items():
        print(f"     {resp_type}: {count} ({count/validation_stats['total_responses']:.1%})")


if __name__ == "__main__":
    example_openshift_analysis()
    example_vllm_analysis()
    example_repetitive_pattern_removal()
    example_integration_with_llm()
    example_response_types()
    example_validation_monitoring()