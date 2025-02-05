from warriors.google import call_gemini


text, finish_reason, reported_model = call_gemini("hi!")
print(text)
print(finish_reason)
print(reported_model)
print(len(text))
