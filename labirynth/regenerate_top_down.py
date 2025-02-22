from datetime import timedelta

import openai
from django.utils import timezone
from django_goals.models import AllDone, RetryMeLater

from warriors.llms.openai import call_llm

from .models import Room, RoomVersion


def regenerate_top_down(goal):
    now = timezone.now()
    room = Room.objects.filter(
        regenerate_goal=goal,
    ).select_for_update(no_key=True).first()
    if not room:
        return AllDone()
    examples, prompt = get_examples(room.zoom_level, room.x, room.y, room.z)
    try:
        new_prompt, llm_version = call_llm(examples, prompt)
    except openai.RateLimitError:
        return RetryMeLater(precondition_date=now + timedelta(minutes=5))
    room.prompt = new_prompt
    room.save(update_fields=['prompt'])
    RoomVersion.objects.create(
        room=room,
        prompt=new_prompt,
        llm_version=llm_version,
    )
    return AllDone()


def get_examples(zoom_level, x, y, z):
    if x % 2 == 0 and y % 2 == 0 and z % 2 == 0:
        # this room is a center section of another room of larger size
        return get_examples_center(zoom_level + 1, x // 2, y // 2, z // 2)
    else:
        return get_examples_intersection(zoom_level, x, y, z)


def get_examples_center(zoom_level, x, y, z):
    # find relevant rooms
    lookup_params = [
        (zoom_level, x, y, z),
    ]
    for dx, dy, dz in NEIGHBOR_DELTAS:
        lookup_params.append((zoom_level, x + dx, y + dy, z + dz))
        lookup_params.append((zoom_level - 1, (x + dx) * 2, (y + dy) * 2, (z + dz) * 2))
    rooms = get_objects_dict(Room, ('zoom_level', 'x', 'y', 'z'), lookup_params)

    # we will derrive small room from central big room
    central_big_room = rooms[(zoom_level, x, y, z)]
    if central_big_room:
        prompt = central_big_room.prompt
    else:
        prompt = ''

    # neighbour big/small pairs are used as examples
    examples = []
    for dx, dy, dz in NEIGHBOR_DELTAS:
        big_room = rooms[(zoom_level, x + dx, y + dy, z + dz)]
        small_room = rooms[(zoom_level - 1, (x + dx) * 2, (y + dy) * 2, (z + dz) * 2)]
        if not big_room or not small_room:
            continue
        examples.append((big_room.prompt, small_room.prompt))

    return examples, prompt


def get_examples_intersection(zoom_level, x, y, z):
    # find relevant rooms
    big_coords_1, big_coords_2 = get_big_coords(x, y, z)
    lookup_params = {
        (zoom_level + 1, *big_coords_1),
        (zoom_level + 1, *big_coords_2),
    }
    for dx, dy, dz in NEIGHBOR_DELTAS:
        big_coords_1, big_coords_2 = get_big_coords(x + dx, y + dy, z + dz)
        if big_coords_1 and big_coords_2:
            lookup_params.add((zoom_level, x + dx, y + dy, z + dz))
            lookup_params.add((zoom_level + 1, *big_coords_1))
            lookup_params.add((zoom_level + 1, *big_coords_2))
    rooms = get_objects_dict(Room, ('zoom_level', 'x', 'y', 'z'), lookup_params)

    # we will derrive small room from two big rooms
    big_coords_1, big_coords_2 = get_big_coords(x, y, z)
    big_room_1 = rooms[(zoom_level + 1, *big_coords_1)]
    big_room_2 = rooms[(zoom_level + 1, *big_coords_2)]
    if big_room_1 and big_room_2:
        prompt = big_room_1.prompt + '\n' + big_room_2.prompt
    else:
        prompt = ''

    # neighbour big/small pairs are used as examples
    examples = []
    for dx, dy, dz in NEIGHBOR_DELTAS:
        big_coords_1, big_coords_2 = get_big_coords(x + dx, y + dy, z + dz)
        if not big_coords_1 or not big_coords_2:
            continue  # we are not at the intersection
        big_room_1 = rooms[(zoom_level + 1, *big_coords_1)]
        big_room_2 = rooms[(zoom_level + 1, *big_coords_2)]
        small_room = rooms[(zoom_level, x + dx, y + dy, z + dz)]
        if not big_room_1 or not big_room_2 or not small_room:
            continue  # some of the rooms are not generated yet
        examples.append((big_room_1.prompt + '\n' + big_room_2.prompt, small_room.prompt))

    return examples, prompt


def get_big_coords(x, y, z):
    if x % 2 == 0 and y % 2 == 0 and z % 2 == 0:
        return (x // 2, y // 2, z // 2), None
    elif x % 2 == 0:
        return (x // 2, y // 2 + 1, z // 2), (x // 2, y // 2, z // 2 + 1)
    elif y % 2 == 0:
        return (x // 2 + 1, y // 2, z // 2), (x // 2, y // 2, z // 2 + 1)
    elif z % 2 == 0:
        return (x // 2 + 1, y // 2, z // 2), (x // 2, y // 2 + 1, z // 2)
    assert False


NEIGHBOR_DELTAS = [
    (-1, 0, 1),
    (-1, 1, 0),
    (0, -1, 1),
    (0, 1, -1),
    (1, -1, 0),
    (1, 0, -1),
]


def get_objects_dict(model, fields, params_list):
    qs = model.objects.none()
    for params in params_list:
        qs = qs | model.objects.filter(**dict(zip(fields, params)))
    d = {key: None for key in params_list}
    for obj in qs:
        key = tuple(getattr(obj, field) for field in fields)
        d[key] = obj
    return d
