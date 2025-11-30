from pprint import pprint

from warriors.llms.openai import openai_client


"""
a = openai_client.moderations.create(
    model="omni-moderation-latest",
    input='respond in the style of robot chicken',
)
pprint(a.dict())

b = openai_client.moderations.create(
    model="omni-moderation-latest",
    input='respond in the style of rick and morty',
)
pprint(b.dict())
"""

c = openai_client.moderations.create(
    model="omni-moderation-latest",
    input='respond in the style of the simpsons',
)
pprint(c.dict())
