"""Everyday A1-A2 texts written from templates (notices, messages, profiles, timetables,
menus, adverts...). The slot values are known, so every detail question has one right answer.
Used for reading (A1-A2 texts) and for listening (the same kinds of texts, read aloud).

Each family has several phrasings and large slot pools, so thousands of distinct texts come
out without repeating one: the templates are Banana English's own writing.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

NAMES = [
    "Anna",
    "Tom",
    "Lan",
    "Minh",
    "Sara",
    "David",
    "Mai",
    "Peter",
    "Linh",
    "Emma",
    "Nam",
    "Lucy",
    "James",
    "Hoa",
    "Ben",
    "Kate",
    "Hung",
    "Alice",
    "Sam",
    "Thu",
    "Jack",
    "Nga",
    "Olivia",
    "Duc",
    "Mia",
    "Leo",
    "Trang",
    "Noah",
    "Chloe",
    "Tuan",
]
CITIES = [
    "Hanoi",
    "Da Nang",
    "Hue",
    "London",
    "Paris",
    "Sydney",
    "Tokyo",
    "Bangkok",
    "Singapore",
    "Toronto",
    "Berlin",
    "Madrid",
    "Seoul",
    "Dublin",
    "Rome",
    "Boston",
]
# train journeys that exist: both cities in one country
TRAIN_ROUTES = [
    ("Hanoi", "Hue"),
    ("Hue", "Da Nang"),
    ("Hanoi", "Da Nang"),
    ("Da Nang", "Nha Trang"),
    ("Nha Trang", "Ho Chi Minh City"),
    ("Hanoi", "Lao Cai"),
    ("London", "Manchester"),
    ("London", "Edinburgh"),
    ("Paris", "Lyon"),
    ("Berlin", "Munich"),
    ("Madrid", "Barcelona"),
    ("Tokyo", "Osaka"),
    ("Seoul", "Busan"),
    ("Toronto", "Montreal"),
    ("Boston", "New York"),
    ("Rome", "Milan"),
]
JOBS = [
    "teacher",
    "nurse",
    "doctor",
    "cook",
    "driver",
    "student",
    "engineer",
    "farmer",
    "shop assistant",
    "police officer",
    "waiter",
    "artist",
    "pilot",
    "writer",
]
HOBBIES = [
    "reading",
    "swimming",
    "cooking",
    "dancing",
    "playing football",
    "drawing",
    "playing the guitar",
    "watching films",
    "running",
    "taking photos",
    "singing",
    "playing chess",
    "gardening",
    "riding a bike",
]
FOODS = [
    "pizza",
    "noodles",
    "rice",
    "fish",
    "chicken",
    "salad",
    "soup",
    "bread",
    "cake",
    "fruit",
    "pasta",
    "eggs",
]
DRINKS = ["tea", "coffee", "orange juice", "milk", "water", "lemonade"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
PLACES = [
    "park",
    "library",
    "cinema",
    "station",
    "museum",
    "café",
    "sports centre",
    "supermarket",
    "school",
    "hospital",
    "bus stop",
    "swimming pool",
]
ITEMS = [
    "some music",
    "a cake",
    "a camera",
    "some drinks",
    "an umbrella",
    "a map",
    "some bread",
    "a football",
    "some games",
    "a blanket",
]
COLORS = ["black", "white", "brown", "grey", "orange", "red", "blue", "green", "yellow"]
PETS = ["cat", "dog", "rabbit", "parrot"]
FAMILY = [
    "parents",
    "sister",
    "brother",
    "grandmother",
    "two brothers",
    "wife",
    "husband",
    "cousin",
    "aunt",
]
WEATHER = ["sunny", "rainy", "cloudy", "windy", "snowy", "foggy"]
ROOMS = ["one bedroom", "two bedrooms", "three bedrooms"]
SUBJECTS = ["maths", "English", "history", "science", "music", "art", "geography"]


def clock(rng: random.Random, start: int = 7, end: int = 21) -> str:
    return f"{rng.randint(start, end)}:{rng.choice(['00', '15', '30', '45'])}"


def other(rng: random.Random, pool: list[str], *not_: str, k: int = 3) -> list[str]:
    choices = [x for x in pool if x not in not_]
    rng.shuffle(choices)
    return choices[:k]


def other_times(rng: random.Random, right: str, k: int = 3) -> list[str]:
    out: list[str] = []
    while len(out) < k:
        t = clock(rng)
        if t != right and t not in out:
            out.append(t)
    return out


def other_numbers(
    rng: random.Random, right: int, lo: int, hi: int, k: int = 3, step: int = 1
) -> list[str]:
    """k numbers in [lo, hi] other than `right`, multiples of `step` like the right one (a
    round 500 among 427 and 483 would give the answer away)."""
    out: list[str] = []
    while len(out) < k:
        n = rng.randint(lo // step, hi // step) * step
        if n != right and str(n) not in out:
            out.append(str(n))
    return out


@dataclass
class TemplateQuestion:
    kind: str  # detail | true_false
    prompt: str
    right: str
    wrong: list[str]
    explanation: str
    explanation_vi: str


@dataclass
class TemplateText:
    family: str
    level: str
    topic: str
    title: str
    text: str
    questions: list[TemplateQuestion] = field(default_factory=list)


def _tf(statement: str, true: bool, evidence: str, vi_evidence: str) -> TemplateQuestion:
    return TemplateQuestion(
        "true_false",
        statement,
        "True" if true else "False",
        ["False" if true else "True"],
        f"The text says: {evidence}",
        f"Bài viết nói: {vi_evidence}",
    )


def _detail(prompt: str, right: str, wrong: list[str], evidence: str) -> TemplateQuestion:
    return TemplateQuestion(
        "detail",
        prompt,
        right,
        wrong,
        f"The text says: {evidence}",
        f"Chi tiết trong bài: {evidence}",
    )


def profile(rng: random.Random) -> TemplateText:
    name, city, job = rng.choice(NAMES), rng.choice(CITIES), rng.choice(JOBS)
    age = rng.randint(9, 60)
    h1, h2 = rng.sample(HOBBIES, 2)
    # a child does not live with a wife or husband
    family = [f for f in FAMILY if age >= 20 or f not in ("wife", "husband")]
    fam = rng.choice(family)
    food = rng.choice(FOODS)
    article = "an" if job[0] in "aeiou" else "a"
    job_line = f"I am {article} {job}." if age >= 20 else "I am a student."
    job = job if age >= 20 else "student"
    text = (
        f"Hello! My name is {name}. I am {age} years old and I live in {city} with my {fam}. "
        f"{job_line} In my free time I like {h1} and {h2}. My favourite food is {food}. "
        f"At the weekend I often visit my friends."
    )
    t = TemplateText("profile", "A1", "family", f"About {name}", text)
    t.questions = [
        _detail(
            f"How old is {name}?",
            str(age),
            other_numbers(rng, age, 9, 60),
            f"I am {age} years old.",
        ),
        _detail(f"Where does {name} live?", city, other(rng, CITIES, city), f"I live in {city}."),
        _detail(
            f"What is {name}'s favourite food?",
            food,
            other(rng, FOODS, food),
            f"My favourite food is {food}.",
        ),
        _tf(f"{name} likes {h1}.", True, f"I like {h1} and {h2}.", f"I like {h1} and {h2}."),
        _tf(
            # never "brother" against "two brothers": both would be true
            f"{name} says: “I live with my "
            f"{rng.choice([f for f in family if f[:5] not in fam and fam[:5] not in f])}.”",
            False,
            f"I live in {city} with my {fam}.",
            f"sống cùng {fam}.",
        ),
    ]
    return t


def notice(rng: random.Random) -> TemplateText:
    place = rng.choice(["library", "swimming pool", "museum", "sports centre", "art gallery"])
    open_, close = clock(rng, 7, 10), clock(rng, 17, 21)
    sat = clock(rng, 12, 16)
    day = rng.choice(DAYS[:5])
    n = rng.randint(2, 6)
    text = (
        f"Welcome to the city {place}! We are open from {open_} to {close}, Monday to "
        f"Friday. On Saturday we close at {sat}, and on Sunday we are closed. Every {day} "
        f"there is a free tour at 11:00. Please do not eat or drink inside. Groups of more "
        f"than {n} people must book first."
    )
    t = TemplateText("notice", "A1", "daily_life", f"City {place.title()}", text)
    t.questions = [
        _detail(
            "What time does it open on weekdays?",
            open_,
            other_times(rng, open_),
            f"We are open from {open_} to {close}, Monday to Friday.",
        ),
        _detail(
            "What time does it close on Saturday?",
            sat,
            other_times(rng, sat),
            f"On Saturday we close at {sat}.",
        ),
        _detail(
            "When is the free tour?",
            f"on {day}",
            [f"on {d}" for d in other(rng, DAYS[:5], day)],
            f"Every {day} there is a free tour.",
        ),
        _tf("It is open on Sunday.", False, "On Sunday we are closed.", "Chủ nhật đóng cửa."),
        _tf(
            "You cannot eat inside.",
            True,
            "Please do not eat or drink inside.",
            "không được ăn uống bên trong.",
        ),
    ]
    return t


def message(rng: random.Random) -> TemplateText:
    sender, to = rng.sample(NAMES, 2)
    place = rng.choice(PLACES)
    event = rng.choice(["film", "concert", "party", "match", "class", "picnic"])
    time = clock(rng, 9, 20)
    item = rng.choice(ITEMS)
    day = rng.choice([d for d in DAYS if d != "Friday"])
    text = (
        f"Hi {to}, it's {sender}. The {event} is on {day}, not Friday. It starts at {time} "
        f"at the {place}. Can you bring {item}? I'll meet you at the entrance ten minutes "
        f"before. Call me if you are late. See you!"
    )
    t = TemplateText("message", "A1", "communication", f"A message from {sender}", text)
    t.questions = [
        _detail(
            f"When is the {event}?",
            f"on {day}",
            [f"on {d}" for d in other(rng, DAYS, day, "Friday", k=2)] + ["on Friday"],
            f"The {event} is on {day}, not Friday.",
        ),
        _detail(
            f"What time does the {event} start?",
            time,
            other_times(rng, time),
            f"It starts at {time}.",
        ),
        _detail(
            f"What should {to} bring?", item, other(rng, ITEMS, item), f"Can you bring {item}?"
        ),
        _tf(f"The {event} is at the {place}.", True, f"at the {place}", f"ở {place}."),
        _tf(
            f"{sender} will meet {to} inside.",
            False,
            "I'll meet you at the entrance.",
            "hẹn gặp ở lối vào.",
        ),
    ]
    return t


def menu(rng: random.Random) -> TemplateText:
    name = rng.choice(["Green", "Sunny", "Blue Moon", "Corner", "Happy", "River", "Old Town"])
    foods = rng.sample(FOODS, 3)
    drink = rng.choice(DRINKS)
    prices = [rng.randint(3, 15) for _ in foods]
    dprice = rng.randint(1, 4)
    open_, close = clock(rng, 7, 10), clock(rng, 20, 22)
    day = rng.choice(DAYS)
    lines = ", ".join(f"{f} {p} dollars" for f, p in zip(foods, prices, strict=True))
    text = (
        f"{name} Café. Today's menu: {lines}. All drinks are {dprice} dollars. Try our "
        f"fresh {drink}! We are open every day from {open_} to {close}, but we are closed "
        f"on {day}. Children under six eat for free."
    )
    t = TemplateText("menu", "A1", "food", f"{name} Café", text)
    t.questions = [
        _detail(
            f"How much is the {foods[0]}?",
            f"{prices[0]} dollars",
            [f"{p} dollars" for p in other_numbers(rng, prices[0], 3, 15)],
            f"{foods[0]} {prices[0]} dollars",
        ),
        _detail(
            "On which day is the café closed?",
            day,
            other(rng, DAYS, day),
            f"we are closed on {day}.",
        ),
        _detail(
            "How much is a drink?",
            f"{dprice} dollars",
            [f"{p} dollars" for p in other_numbers(rng, dprice, 1, 9)],
            f"All drinks are {dprice} dollars.",
        ),
        _tf(
            "Young children do not pay for food.",
            True,
            "Children under six eat for free.",
            "trẻ em dưới sáu tuổi ăn miễn phí.",
        ),
        _tf(
            f"The café closes at {other_times(rng, close, 1)[0]}.",
            False,
            f"We are open every day from {open_} to {close}.",
            f"mở cửa đến {close}.",
        ),
    ]
    return t


def timetable(rng: random.Random) -> TemplateText:
    a, b = rng.sample(rng.choice(TRAIN_ROUTES), 2)
    dep = clock(rng, 6, 18)
    hours = rng.randint(2, 7)  # never "about 1 hours"
    platform = rng.randint(1, 12)
    price = rng.randint(10, 90)
    text = (
        f"Train information. The next train to {b} leaves {a} at {dep} from platform "
        f"{platform}. The journey takes about {hours} hours. A ticket costs {price} "
        f"dollars, and students pay half price. There is a café on the train. Please have "
        f"your ticket ready."
    )
    t = TemplateText("timetable", "A2", "travel", f"Train to {b}", text)
    t.questions = [
        _detail(
            f"Which platform does the train to {b} leave from?",
            f"platform {platform}",
            [f"platform {n}" for n in other_numbers(rng, platform, 1, 12)],
            f"from platform {platform}",
        ),
        _detail(
            "What time does the train leave?", dep, other_times(rng, dep), f"leaves {a} at {dep}"
        ),
        _detail(
            "How long is the journey?",
            f"about {hours} hours",
            [f"about {n} hours" for n in other_numbers(rng, hours, 2, 9)],
            f"The journey takes about {hours} hours.",
        ),
        _tf("Students pay less.", True, "students pay half price", "sinh viên được giảm một nửa."),
        _tf(
            "You can't buy food on the train.",
            False,
            "There is a café on the train.",
            "trên tàu có quán cà phê.",
        ),
    ]
    return t


def weather(rng: random.Random) -> TemplateText:
    city = rng.choice(CITIES)
    w1, w2 = rng.sample(WEATHER, 2)
    # a real forecast: near zero when it snows, and the afternoon a few degrees off the morning
    lo, hi = (-4, 4) if "snowy" in (w1, w2) else (12, 34)
    t1 = rng.randint(lo, hi)
    t2 = t1 + rng.choice([-3, -2, 2, 3, 4, 5, 6])
    day = rng.choice(DAYS)
    text = (
        f"Here is the weather for {city}. This morning it will be {w1}, with a temperature "
        f"of {t1} degrees. In the afternoon it will be {w2} and the temperature will be "
        f"{t2} degrees. On {day} the weather will be better. Take an umbrella if you go "
        f"out tonight."
    )
    t = TemplateText("weather", "A2", "nature", f"Weather in {city}", text)
    t.questions = [
        _detail(
            "What will the weather be like this morning?",
            w1,
            other(rng, WEATHER, w1),
            f"This morning it will be {w1}.",
        ),
        _detail(
            "What will the temperature be in the afternoon?",
            f"{t2} degrees",
            [f"{n} degrees" for n in other_numbers(rng, t2, t2 - 8, t2 + 8)],
            f"the temperature will be {t2} degrees",
        ),
        _detail(
            "When will the weather be better?",
            f"on {day}",
            [f"on {d}" for d in other(rng, DAYS, day)],
            f"On {day} the weather will be better.",
        ),
        _tf(
            "You may need an umbrella tonight.",
            True,
            "Take an umbrella if you go out tonight.",
            "mang theo ô nếu ra ngoài tối nay.",
        ),
        _tf(
            f"The forecast is for {rng.choice([c for c in CITIES if c != city])}.",
            False,
            f"Here is the weather for {city}.",
            f"dự báo cho {city}.",
        ),
    ]
    return t


def advert(rng: random.Random) -> TemplateText:
    city = rng.choice(CITIES)
    rooms = rng.choice(ROOMS)
    price = rng.randint(4, 20) * 50
    floor = rng.randint(1, 12)
    name = rng.choice(NAMES)
    phone_end = rng.randint(100, 999)
    text = (
        f"Flat for rent in {city}. The flat has {rooms}, a kitchen and a small balcony. It "
        f"is on the {_ordinal(floor)} floor, and there is a lift. The rent is {price} "
        f"dollars a month. Pets are not allowed. It is near a park and a bus stop. Call "
        f"{name} on 0912 555 {phone_end}."
    )
    t = TemplateText("advert", "A2", "home", f"Flat in {city}", text)
    t.questions = [
        _detail(
            "How much is the rent?",
            f"{price} dollars a month",
            [f"{p} dollars a month" for p in other_numbers(rng, price, 200, 1000, step=50)],
            f"The rent is {price} dollars a month.",
        ),
        _detail(
            "Which floor is the flat on?",
            f"the {_ordinal(floor)} floor",
            [f"the {_ordinal(int(n))} floor" for n in other_numbers(rng, floor, 1, 12)],
            f"It is on the {_ordinal(floor)} floor.",
        ),
        _detail("Who should you call?", name, other(rng, NAMES, name), f"Call {name}."),
        _tf(
            "You can keep a dog in the flat.",
            False,
            "Pets are not allowed.",
            "không được nuôi thú cưng.",
        ),
        _tf("There is a lift in the building.", True, "there is a lift", "có thang máy."),
    ]
    return t


def lost_pet(rng: random.Random) -> TemplateText:
    pet, color = rng.choice(PETS), rng.choice(COLORS)
    name = rng.choice(["Max", "Bella", "Coco", "Milo", "Luna", "Kiki", "Rocky", "Mimi"])
    place = rng.choice(PLACES)
    day = rng.choice(DAYS)
    owner = rng.choice(NAMES)
    reward = rng.randint(2, 10) * 10
    text = (
        f"Lost {pet}! Our {pet} {name} is {color} and very friendly. We lost {name} near "
        f"the {place} on {day} evening. {name} is wearing a red collar. If you see {name}, "
        f"please call {owner}. There is a reward of {reward} dollars. Thank you!"
    )
    t = TemplateText("lost_pet", "A1", "nature", f"Lost {pet}: {name}", text)
    t.questions = [
        _detail(
            f"What colour is {name}?",
            color,
            other(rng, COLORS, color, "red"),
            f"{name} is {color}.",
        ),
        _detail(
            f"Where did they lose {name}?",
            f"near the {place}",
            [f"near the {p}" for p in other(rng, PLACES, place)],
            f"We lost {name} near the {place}.",
        ),
        _detail(
            "How big is the reward?",
            f"{reward} dollars",
            [f"{n} dollars" for n in other_numbers(rng, reward, 20, 100, step=10)],
            f"There is a reward of {reward} dollars.",
        ),
        _tf(f"{name} is wearing a collar.", True, "wearing a red collar", "đeo vòng cổ màu đỏ."),
        _tf(f"They lost {name} in the morning.", False, f"on {day} evening", f"vào tối {day}."),
    ]
    return t


def school_day(rng: random.Random) -> TemplateText:
    name = rng.choice(NAMES)
    s1, s2, s3 = rng.sample(SUBJECTS, 3)
    start, lunch = clock(rng, 7, 8), clock(rng, 11, 12)
    end = clock(rng, 15, 17)
    sport = rng.choice(["football", "basketball", "badminton", "volleyball", "tennis"])
    day = rng.choice(DAYS[:5])
    text = (
        f"{name}'s school day starts at {start}. The first lesson is {s1}, and then {s2}. "
        f"Lunch is at {lunch} in the school canteen. In the afternoon {name} has {s3}. "
        f"School finishes at {end}. On {day} {name} plays {sport} after school. {name}'s "
        f"favourite subject is {s2}."
    )
    t = TemplateText("school_day", "A1", "education", f"{name}'s school day", text)
    t.questions = [
        _detail(
            "What is the first lesson?", s1, other(rng, SUBJECTS, s1), f"The first lesson is {s1}."
        ),
        _detail("What time is lunch?", lunch, other_times(rng, lunch), f"Lunch is at {lunch}."),
        _detail(
            f"What does {name} play on {day}?",
            sport,
            other(rng, ["football", "basketball", "badminton", "volleyball", "tennis"], sport),
            f"On {day} {name} plays {sport}.",
        ),
        _tf(
            f"{name}'s favourite subject is {s1}.",
            s1 == s2,
            f"favourite subject is {s2}.",
            f"môn yêu thích là {s2}.",
        ),
        _tf(f"{name} has lunch at home.", False, "in the school canteen", "ăn trưa ở căng tin."),
    ]
    return t


def _ordinal(n: int) -> str:
    return {1: "first", 2: "second", 3: "third"}.get(n) or (f"{n}th" if n > 3 else str(n))


FAMILIES: dict[str, Callable[[random.Random], TemplateText]] = {
    "profile": profile,
    "notice": notice,
    "message": message,
    "menu": menu,
    "timetable": timetable,
    "weather": weather,
    "advert": advert,
    "lost_pet": lost_pet,
    "school_day": school_day,
}


def generate(count: int, seed: str) -> Iterator[TemplateText]:
    """`count` distinct texts, spread over the families."""
    rng = random.Random(seed)
    seen: set[str] = set()
    families = list(FAMILIES.values())
    tries = 0
    while len(seen) < count and tries < count * 20:
        tries += 1
        t = families[len(seen) % len(families)](rng)
        if t.text in seen:
            continue
        seen.add(t.text)
        yield t
