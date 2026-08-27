import dspy

def configure_llm():
    lm = dspy.LM(
        'openai/gemma-4-E2B-it-IQ4_XS',
        api_base='http://localhost:1337/v1',
        api_key='not-needed',
    )
    dspy.configure(lm=lm)