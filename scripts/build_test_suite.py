"""Build the SoraLink held-out test suite: curated cases + generated stress cases.

Run::

    python scripts/build_test_suite.py

The 950 hand-written cases in ``data/test_suite.json`` are preserved verbatim
(``source: curated``); everything else is regenerated deterministically
(``source: generated``) from per-intent phrase banks crossed with register-specific
request frames, plus generated failure probes (gibberish, symbols, wrong script,
out-of-domain questions, degenerate input).

Generated cases never appear in ``data/intents.json`` training data, and the
curated block stays untouched, so its metrics remain comparable over time.

Output: ``data/test_suite.json`` with 6,450 cases (4,450 intent + 2,000 failure),
where every failure probe is an input for which **no catalog intent matches** and the
correct behaviour is to abstain or ask, never to auto-file.
"""

from __future__ import annotations

import itertools
import json
import random
import string
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = PROJECT_ROOT / "data" / "test_suite.json"
CATALOG_PATH = PROJECT_ROOT / "data" / "intents.json"

TARGET_INTENT_GENERATED = 3550
TARGET_FAILURE_GENERATED = 1950  # + 50 curated failure probes = 2,000 negatives
TARGET_TOTAL = 950 + TARGET_INTENT_GENERATED + TARGET_FAILURE_GENERATED

#: Generated in-domain cases per register, per intent (sums to 236 per intent;
#: the first 10 intents get one extra case each to reach 3,550 exactly).
REGISTER_TARGETS = {
    "en": 56,
    "asr": 36,
    "hinglish": 36,
    "hi": 32,
    "pa": 28,
    "ja": 24,
    "edge": 24,
}

FRAMES: dict[str, list[str]] = {
    "en": [
        "{p}",
        "{p} please",
        "Can I get {p}",
        "Could you bring me {p}",
        "I need {p}",
        "Please get me {p}",
        "Is {p} available",
        "Could I have {p}",
    ],
    "asr": [
        "{p}",
        "{p} please",
        "need {p}",
        "any {p}",
        "{p} now",
        "get {p}",
        "give {p}",
        "i want {p}",
        "{p} pls",
        "bring {p}",
    ],
    "hinglish": [
        "{p} chahiye",
        "mujhe {p} chahiye",
        "{p} mil sakta hai",
        "{p} de dijiye",
        "{p} milega kya",
        "please {p} de do",
        "{p} chahiye please",
        "{p} do",
        "mujhe {p} do",
        "{p} la do",
    ],
    "hi": [
        "मुझे {p} चाहिए",
        "{p} दीजिए",
        "{p} मिल सकता है",
        "कृपया {p} दीजिए",
        "{p} है क्या",
        "मुझे {p} की ज़रूरत है",
        "{p} लाइए",
        "{p} चाहिए",
        "{p} दो",
        "{p} उपलब्ध है",
        "एक {p} मिलेगा",
    ],
    "pa": [
        "{p} ਦਿਓ",
        "{p} ਮਿਲ ਸਕਦਾ ਹੈ",
        "ਕਿਰਪਾ ਕਰਕੇ {p} ਦਿਓ",
        "{p} ਹੈ ਕੀ",
        "{p} ਲਿਆਓ",
        "{p} ਦੇ ਦਿਓ",
        "{p} ਦੇਣਾ",
        "{p} ਲੈ ਆਓ",
        "{p} ਉਪਲਬਧ ਹੈ",
    ],
    "ja": [
        "{p}をください",
        "{p}はありますか",
        "{p}をお願いします",
        "{p}をもらえますか",
        "{p}がほしいです",
        "すみません、{p}をお願いします",
        "{p}をいただけますか",
    ],
    "edge": ["{P}!!!", "{p} plz", "{p} asap", "{p} pls now", "{p}?", "{p} please!!"],
}

#: Per-intent noun phrases per register. Kept as noun phrases so every frame
#: produces a request-shaped utterance (some awkward, all ASR-plausible).
PHRASES: dict[str, dict[str, list[str]]] = {
    "medical_help": {
        "en": ["a doctor", "a nurse", "medical help", "an ambulance", "oxygen", "my medicine", "medical assistance", "a first aid kit"],
        "asr": ["doctor", "medical help", "oxygen", "my medicine", "nurse", "ambulance"],
        "hinglish": ["doctor", "medical help", "oxygen", "meri dawa", "ambulance", "nurse"],
        "hi": ["डॉक्टर", "नर्स", "मेडिकल मदद", "ऑक्सीजन", "मेरी दवाई"],
        "pa": ["ਡਾਕਟਰ", "ਨਰਸ", "ਮੈਡੀਕਲ ਮਦਦ", "ਆਕਸੀਜਨ", "ਮੇਰੀ ਦਵਾਈ"],
        "ja": ["医者", "看護師", "酸素", "私の薬", "救急車"],
        "edge": ["doctor!!", "medical help", "oxygen", "doctor asap", "nurse plz", "medicine"],
    },
    "accessibility_assist": {
        "en": ["a wheelchair", "an interpreter", "wheelchair assistance", "braille assistance", "sign language support", "someone to guide me", "extra time boarding", "assistance walking"],
        "asr": ["wheelchair", "interpreter", "wheelchair help", "sign language", "guide me", "walking assistance"],
        "hinglish": ["wheelchair", "interpreter", "wheelchair ki madad", "sign language", "guide chahiye", "chalne mein madad"],
        "hi": ["व्हीलचेयर", "दुभाषिया", "व्हीलचेयर की मदद", "साइन लैंग्वेज", "चलने में मदद"],
        "pa": ["ਵ੍ਹੀਲਚੇਅਰ", "ਦੁਭਾਸ਼ੀਆ", "ਵ੍ਹੀਲਚੇਅਰ ਦੀ ਮਦਦ", "ਸਾਈਨ ਲੈਂਗਵੇਜ", "ਤੁਰਨ ਵਿੱਚ ਮਦਦ"],
        "ja": ["車椅子", "通訳", "車椅子の手伝い", "手話", "歩くのを手伝って"],
        "edge": ["WHEELCHAIR", "interpreter plz", "wheelchair help", "sign language!!", "guide me plz", "braille assistance"],
    },
    "safety_concern": {
        "en": ["security", "the crew", "police", "help", "a crew member", "a supervisor", "cabin security", "the authorities"],
        "asr": ["security", "crew", "police", "help urgently", "security now", "crew help"],
        "hinglish": ["security", "crew", "police", "madad chahiye", "security guard", "help chahiye"],
        "hi": ["सुरक्षा", "क्रू", "पुलिस", "मदद चाहिए", "सुरक्षा गार्ड"],
        "pa": ["ਸੁਰੱਖਿਆ", "ਕਰੂ", "ਪੁਲਿਸ", "ਮਦਦ ਚਾਹੀਦੀ ਹੈ", "ਸਿਕਿਊਰਿਟੀ"],
        "ja": ["警備員", "警察", "乗務員", "助けて", "担当者"],
        "edge": ["SECURITY!!", "crew now", "police", "help!!!", "security plz", "crew asap"],
    },
    "motion_sickness": {
        "en": ["a sick bag", "a vomit bag", "nausea medicine", "something for nausea", "dizziness tablets", "anti nausea medicine", "a sick bag urgently", "nausea tablets"],
        "asr": ["sick bag", "sick bag now", "nausea medicine", "motion sickness tablet", "sick bag please", "nausea tablets"],
        "hinglish": ["sick bag", "ulti ka bag", "ulti ki dawa", "chakkar ki dawa", "ulti ho rahi hai", "sick bag please"],
        "hi": ["उल्टी की थैली", "उल्टी की दवाई", "चक्कर की दवाई", "उल्टी हो रही है", "सिक बैग"],
        "pa": ["ਉਲਟੀ ਦਾ ਬੈਗ", "ਉਲਟੀ ਦੀ ਦਵਾਈ", "ਚੱਕਰ ਦੀ ਦਵਾਈ", "ਉਲਟੀ ਹੋ ਰਹੀ ਹੈ", "ਸਿੱਕ ਬੈਗ"],
        "ja": ["吐き気止め", "酔い止め", "吐き気がする", "吐き気止めの薬", "酔い止めの薬"],
        "edge": ["SICK BAG", "sick bag now", "nausea meds", "dizzy tablets asap", "sick bag plz", "vomit bag"],
    },
    "water_request": {
        "en": ["some water", "a glass of water", "a water bottle", "cold water", "warm water", "water without ice", "a jug of water", "drinking water"],
        "asr": ["water", "glass water", "water bottle", "cold water", "water now", "water please"],
        "hinglish": ["paani", "thanda paani", "garam paani", "paani ki bottle", "ek glass paani", "normal paani"],
        "hi": ["पानी", "ठंडा पानी", "गरम पानी", "पानी की बोतल", "एक गिलास पानी"],
        "pa": ["ਪਾਣੀ", "ਠੰਡਾ ਪਾਣੀ", "ਗਰਮ ਪਾਣੀ", "ਪਾਣੀ ਦੀ ਬੋਤਲ", "ਇੱਕ ਗਲਾਸ ਪਾਣੀ"],
        "ja": ["お水", "冷たいお水", "温かいお水", "お水のボトル", "お湯"],
        "edge": ["WATER!!", "paani", "water plz", "water asap", "paani chahiye", "water"],
    },
    "blanket_request": {
        "en": ["a blanket", "one more blanket", "a warm blanket", "an extra blanket", "a blanket for my child", "a second blanket", "a clean blanket", "a thin blanket"],
        "asr": ["blanket", "one blanket", "extra blanket", "blanket now", "warm blanket", "blanket please"],
        "hinglish": ["kambal", "ek kambal", "garam kambal", "doosra kambal", "kambal please", "bache ka kambal"],
        "hi": ["कंबल", "एक कंबल", "गरम कंबल", "दूसरा कंबल", "बच्चे का कंबल"],
        "pa": ["ਕੰਬਲ", "ਇੱਕ ਕੰਬਲ", "ਗਰਮ ਕੰਬਲ", "ਦੂਜਾ ਕੰਬਲ", "ਬੱਚੇ ਦਾ ਕੰਬਲ"],
        "ja": ["毛布", "温かい毛布", "もう一枚の毛布", "子供用の毛布", "予備の毛布"],
        "edge": ["BLANKET", "kambal plz", "blanket asap", "kambal chahiye", "blanket!!", "extra blanket"],
    },
    "pillow_request": {
        "en": ["a pillow", "one more pillow", "a soft pillow", "a small pillow", "a pillow for my neck", "an extra pillow", "a clean pillow", "a pillow cover"],
        "asr": ["pillow", "one pillow", "extra pillow", "soft pillow", "pillow now", "pillow please"],
        "hinglish": ["takiya", "ek takiya", "naram takiya", "chhota takiya", "takiya please", "bache ka takiya"],
        "hi": ["तकिया", "एक तकिया", "नरम तकिया", "छोटा तकिया", "बच्चे का तकिया"],
        "pa": ["ਤਕੀਆ", "ਇੱਕ ਤਕੀਆ", "ਨਰਮ ਤਕੀਆ", "ਛੋਟਾ ਤਕੀਆ", "ਬੱਚੇ ਦਾ ਤਕੀਆ"],
        "ja": ["枕", "柔らかい枕", "小さな枕", "子供用の枕", "予備の枕"],
        "edge": ["PILLOW", "takiya plz", "pillow asap", "takiya chahiye", "pillow!!", "extra pillow"],
    },
    "bag_help": {
        "en": ["help with my bag", "a hand with my suitcase", "help lifting my luggage", "help with my backpack", "someone to stow my bag", "help with my trolley", "help with the overhead bin", "help with my bag down"],
        "asr": ["bag help", "help bag", "suitcase help", "lift bag", "bag down", "help luggage"],
        "hinglish": ["bag help", "madad bag ke liye", "suitcase uthane mein madad", "bag rakhne mein madad", "bag ki madad", "luggage help"],
        "hi": ["बैग में मदद", "सामान उठाने में मदद", "सूटकेस में मदद", "बैग रखने में मदद", "सामान की मदद"],
        "pa": ["ਬੈਗ ਵਿੱਚ ਮਦਦ", "ਸਮਾਨ ਚੁੱਕਣ ਵਿੱਚ ਮਦਦ", "ਸੂਟਕੇਸ ਵਿੱਚ ਮਦਦ", "ਬੈਗ ਰੱਖਣ ਵਿੱਚ ਮਦਦ", "ਸਮਾਨ ਦੀ ਮਦਦ"],
        "ja": ["荷物の手伝い", "スーツケースの手伝い", "手荷物の手伝い", "バッグの手伝い", "棚への荷物の手伝い"],
        "edge": ["BAG HELP", "bag help plz", "suitcase help", "bag asap", "help bag!!", "luggage help"],
    },
    "headphone_request": {
        "en": ["headphones", "earphones", "a new headset", "a working headphone", "an adapter", "help with the screen", "a remote", "help with the entertainment"],
        "asr": ["headphones", "earphones", "headset", "screen help", "remote", "headphones please"],
        "hinglish": ["headphone", "earphone", "naya headphone", "remote", "screen help", "headphone please"],
        "hi": ["हेडफोन", "ईयरफोन", "नया हेडफोन", "रिमोट", "स्क्रीन में मदद"],
        "pa": ["ਹੈੱਡਫੋਨ", "ਈਅਰਫੋਨ", "ਨਵਾਂ ਹੈੱਡਫੋਨ", "ਰਿਮੋਟ", "ਸਕ੍ਰੀਨ ਵਿੱਚ ਮਦਦ"],
        "ja": ["ヘッドホン", "イヤホン", "新しいヘッドホン", "リモコン", "画面の手伝い"],
        "edge": ["HEADPHONES", "headphone plz", "earphones asap", "headphone!!", "remote", "headset"],
    },
    "meal_inquiry": {
        "en": ["the meal", "the vegetarian meal", "the chicken meal", "a snack", "some food", "the fish meal", "a dessert", "the kids meal"],
        "asr": ["meal", "veg meal", "snack", "food", "meal now", "chicken meal"],
        "hinglish": ["khana", "veg khana", "chicken khana", "snack", "khana please", "mithai"],
        "hi": ["खाना", "वेज खाना", "चिकन खाना", "नाश्ता", "मिठाई"],
        "pa": ["ਖਾਣਾ", "ਵੈਜ ਖਾਣਾ", "ਚਿਕਨ ਖਾਣਾ", "ਸਨੈਕ", "ਮਿਠਾਈ"],
        "ja": ["食事", "ベジタリアン料理", "チキン料理", "軽食", "デザート"],
        "edge": ["FOOD", "khana", "meal plz", "food asap", "khana chahiye", "veg meal"],
    },
    "tea_coffee": {
        "en": ["a cup of tea", "a coffee", "a black tea", "a green tea", "a coffee with milk", "a masala tea", "a decaf coffee", "a lemon tea"],
        "asr": ["tea", "coffee", "chai", "green tea", "coffee now", "tea please"],
        "hinglish": ["chai", "coffee", "masala chai", "green tea", "doodh wali chai", "coffee please"],
        "hi": ["चाय", "कॉफ़ी", "मसाला चाय", "ग्रीन टी", "दूध वाली चाय"],
        "pa": ["ਚਾਹ", "ਕੌਫੀ", "ਮਸਾਲਾ ਚਾਹ", "ਗ੍ਰੀਨ ਟੀ", "ਦੁੱਧ ਵਾਲੀ ਚਾਹ"],
        "ja": ["お茶", "コーヒー", "ミルクティー", "緑茶", "レモンティー"],
        "edge": ["CHAI", "coffee plz", "tea asap", "chai!!", "coffee", "tea"],
    },
    "lavatory_assist": {
        "en": ["the lavatory", "the washroom", "the toilet", "the bathroom", "a clean lavatory", "the restroom", "help with the lavatory door", "the toilet at the back"],
        "asr": ["toilet", "washroom", "lavatory", "restroom", "toilet now", "washroom please"],
        "hinglish": ["toilet", "washroom", "bathroom", "saaf toilet", "toilet please", "washroom kahan"],
        "hi": ["टॉयलेट", "वॉशरूम", "शौचालय", "साफ़ टॉयलेट", "बाथरूम"],
        "pa": ["ਟਾਇਲਟ", "ਵਾਸ਼ਰੂਮ", "ਸ਼ੌਚਾਲਿਆ", "ਸਾਫ਼ ਟਾਇਲਟ", "ਬਾਥਰੂਮ"],
        "ja": ["トイレ", "お手洗い", "洗面所", "きれいなトイレ", "後ろのトイレ"],
        "edge": ["TOILET", "washroom plz", "toilet asap", "loo", "toilet!!", "bathroom"],
    },
    "seat_issue": {
        "en": ["help with my seat", "a working seat", "help with the seat belt", "help with the tray table", "help with the armrest", "a different seat", "help finding my seat", "help with the seat light"],
        "asr": ["seat help", "seat belt", "tray table", "armrest", "seat broken", "seat change"],
        "hinglish": ["seat help", "seat belt help", "tray table help", "armrest help", "seat badal do", "seat kharab hai"],
        "hi": ["सीट में मदद", "सीट बेल्ट में मदद", "ट्रे टेबल में मदद", "आर्मरेस्ट में मदद", "सीट बदलनी है"],
        "pa": ["ਸੀਟ ਵਿੱਚ ਮਦਦ", "ਸੀਟ ਬੈਲਟ ਵਿੱਚ ਮਦਦ", "ਟ੍ਰੇ ਟੇਬਲ ਵਿੱਚ ਮਦਦ", "ਆਰਮਰੈਸਟ ਵਿੱਚ ਮਦਦ", "ਸੀਟ ਬਦਲਣੀ ਹੈ"],
        "ja": ["座席の手伝い", "シートベルトの手伝い", "テーブルの手伝い", "肘掛けの手伝い", "席の変更"],
        "edge": ["SEAT HELP", "seat plz", "seat belt!!", "tray help", "seat asap", "seat change"],
    },
    "customs_form": {
        "en": ["the customs form", "the immigration form", "an arrival card", "a landing card", "a pen", "a declaration form", "the arrival form", "a second form"],
        "asr": ["customs form", "arrival card", "immigration form", "declaration form", "form please", "pen"],
        "hinglish": ["customs form", "immigration form", "arrival card", "form", "pen", "form please"],
        "hi": ["कस्टम फ़ॉर्म", "इमिग्रेशन फ़ॉर्म", "अराइवल कार्ड", "फ़ॉर्म", "पेन"],
        "pa": ["ਕਸਟਮ ਫ਼ਾਰਮ", "ਇਮੀਗ੍ਰੇਸ਼ਨ ਫ਼ਾਰਮ", "ਅਰਾਈਵਲ ਕਾਰਡ", "ਫ਼ਾਰਮ", "ਪੈਨ"],
        "ja": ["税関申告書", "入国カード", "到着カード", "申告書", "ペン"],
        "edge": ["CUSTOMS FORM", "form plz", "arrival card asap", "form!!", "declaration form", "pen please"],
    },
    "baby_care": {
        "en": ["warm milk", "a clean diaper", "the bassinet", "baby food", "a baby bottle", "baby wipes", "formula", "a changing area"],
        "asr": ["baby milk", "diaper", "bassinet", "formula", "baby bottle", "milk warm"],
        "hinglish": ["bache ka doodh", "diaper", "bassinet", "formula milk", "bache ka bottle", "bottle"],
        "hi": ["बच्चे का दूध", "डायपर", "बेसिनेट", "फ़ॉर्मूला मिल्क", "बच्चे की बोतल"],
        "pa": ["ਬੱਚੇ ਦਾ ਦੁੱਧ", "ਡਾਇਪਰ", "ਬੇਸਿਨੇਟ", "ਫ਼ਾਰਮੂਲਾ ਦੁੱਧ", "ਬੱਚੇ ਦੀ ਬੋਤਲ"],
        "ja": ["ミルク", "おむつ", "ベビーベッド", "粉ミルク", "離乳食"],
        "edge": ["BABY MILK", "diaper plz", "bassinet asap", "baby food!!", "formula", "milk warm"],
    },
}

WRONG_SCRIPT = {
    "zh": ["我需要水", "厕所在哪里", "我想吃饭", "叫医生", "这是哪里", "请给我一杯水", "我的座位在哪里", "我要下飞机"],
    "ru": ["где туалет", "мне нужна вода", "позовите врача", "я голоден", "какой это рейс", "сколько это стоит", "дайте мне воду", "где выход"],
    "ar": ["أريد ماء", "أين الحمام", "أحتاج طبيب", "أنا جائع", "ما هذا", "كم السعر", "أعطني ماء", "أين المخرج"],
    "ko": ["화장실 어디예요", "물 주세요", "의사 불러 주세요", "배고파요", "이게 뭐예요", "물 한 잔 주세요", "얼마예요", "출구가 어디예요"],
    "ta": ["தண்ணீர் வேண்டும்", "கழிவறை எங்கே", "மருத்துவரை அழைக்கவும்", "எனக்கு பசி", "இது என்ன", "ஒரு தண்ணீர் குடுங்கள்", "விலை என்ன", "வெளியே எங்கே"],
    "th": ["ฉันต้องการน้ำ", "ห้องน้ำอยู่ที่ไหน", "เรียกหมอให้หน่อย", "ฉันหิว", "นี่คืออะไร", "ขอน้ำหน่อย", "ราคาเท่าไหร่", "ทางออกอยู่ไหน"],
    "el": ["θέλω νερό", "πού είναι η τουαλέτα", "φωνάξτε γιατρό", "πεινάω", "τι είναι αυτό", "πόσο κάνει", "δώστε μου νερό", "πού είναι η έξοδος"],
    "he": ["אני רוצה מים", "איפה השירותים", "תקרא לרופא", "אני רעב", "מה זה", "כמה זה עולה", "תן לי מים", "איפה היציאה"],
}

#: Out-of-scope topics. Deliberately none of them is a catalog noun (water,
#: blanket, pillow, lavatory, meal, tea, headphone, seat, customs form, baby,
#: medical, wheelchair, security), so the only correct outcome is rejection.
OOD_TOPICS = [
    "the wifi password", "the wi-fi code", "a sim card", "a power adapter",
    "a charging port", "a usb socket", "a seat upgrade", "an upgrade voucher",
    "a refund", "my connecting flight", "the connecting gate", "the arrival time",
    "the gate number", "baggage claim", "lost luggage", "a luggage tag",
    "a taxi", "the airport shuttle", "the hotel booking", "the hotel voucher",
    "currency exchange", "the exchange rate", "a receipt", "an invoice",
    "the duty free catalogue", "duty free shopping", "the duty free allowance",
    "the loyalty program", "my miles", "a boarding pass", "the flight status",
    "the flight number", "the departure board", "the departure gate",
    "the landing time", "the weather in tokyo", "a rental car", "the train schedule",
    "airport parking", "the customs duty limit", "a printed ticket",
    "the in-flight magazine", "a souvenir", "a phone charger", "the power outlet",
    "the entertainment guide", "the movie list", "a movie playing tonight",
    "the wine list", "a beer", "a whisky", "the duty free shop",
    "a hotel recommendation", "a shopping discount", "the airline app",
    "the streaming service", "travel insurance", "the visa requirements",
    "the queue time", "the boarding group number", "the wifi speed",
    "the airport lounge", "lounge access", "a shower at the lounge",
    "a laundry service", "a shoe shine", "a newspaper", "a magazine",
    "a postcard", "a stamp", "a notebook", "the gift shop", "a vending machine",
    "the ice machine", "the reading lamp", "the air vent", "the cabin temperature",
    "the heating", "the air conditioning", "the noise level",
    "the turbulence forecast", "a skincare set", "perfume prices",
]
#: Generic question shapes; grammatical for nearly any topic above.
OOD_TEMPLATES = [
    "what is {t}", "where can i find {t}", "how much is {t}", "is {t} free",
    "do you have {t}", "how do i use {t}", "when can i get {t}",
    "can you explain {t}", "who handles {t}", "is {t} available on this flight",
    "i would like to buy {t}", "do i need {t}", "can you tell me about {t}",
    "how do i pay for {t}",
]

#: Statements and social chatter: real speech with no request in it.
STATEMENTS = [
    "thank you so much", "thanks a lot", "good morning", "good evening",
    "good night", "this is my first flight", "i am going to tokyo",
    "i am travelling with my family", "my name is rahul",
    "the flight was very smooth", "i enjoyed the flight", "i am feeling sleepy",
    "i am tired", "nice to meet you", "happy birthday", "happy new year",
    "i love this airline", "the crew was very kind", "i will fly again",
    "see you later", "have a good day", "i am from india", "we are on holiday",
    "i am waiting for my friend", "the view is beautiful", "i took many photos",
    "i am reading a book", "i watched two films", "the landing was smooth",
    "i slept for three hours", "my wife is sleeping", "my son is excited",
    "i am going home", "i will visit kyoto", "the service was excellent",
    "i am happy with the service", "that is all thank you", "nothing else thanks",
    "okay thank you", "i am nervous about flying",
]

#: Bare fillers: grammatical fragments carrying no request at all.
FILLERS = [
    "please", "yes", "ok", "uh", "um", "hmm", "so", "and", "the", "a",
    "okay", "thanks", "no", "maybe", "well", "hello",
]

CONSONANTS = "bcdfghjklmnpqrstvwxyz"
VOWELS = "aeiou"
EMOJI = ["🔥", "🚀", "😀", "✈️", "👍", "❄️", "🥤", "🍱", "🧳", "🛏️"]


def key(text: str) -> str:
    return " ".join(str(text).split()).strip().casefold()


def clean(text: str) -> str:
    return " ".join(str(text).split()).strip()


def load_training_texts() -> set[str]:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {key(example) for entry in catalog["intents"] for example in entry["training_examples"]}


def load_catalog_vocabulary() -> set[str]:
    """Content tokens the catalog knows (mirrors classifier.request_vocabulary)."""
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    import re

    token_re = re.compile(r"[\w\u0900-\u097F\u0A00-\u0A7F']+", re.UNICODE)
    vocabulary: set[str] = set()
    for entry in catalog["intents"]:
        chunks = [entry["intent_id"].replace("_", " ")]
        chunks.extend(entry.get("training_examples", []))
        chunks.extend(entry.get("urgent_keywords", []))
        chunks.extend((entry.get("labels") or {}).values())
        for chunk in chunks:
            vocabulary.update(token.casefold() for token in token_re.findall(str(chunk)))
    return vocabulary


def pseudo_word(rng: random.Random) -> str:
    length = rng.randint(3, 6)
    letters = []
    for index in range(length):
        pool = CONSONANTS if index % 2 == 0 else VOWELS
        letters.append(rng.choice(pool))
    return "".join(letters)


def generate_intent_cases(seen: set[str], target_extra: int) -> list[dict]:
    cases: list[dict] = []
    per_intent: dict[str, int] = {}
    for intent_index, (intent_id, registers) in enumerate(PHRASES.items()):
        made = 0
        for register, wanted in REGISTER_TARGETS.items():
            if register == "en" and intent_index < target_extra:
                wanted += 1
            frames = FRAMES[register]
            phrases = registers[register]
            combos = [clean(frame.format(p=phrase, P=phrase.upper())) for frame in frames for phrase in phrases]
            rng = random.Random(f"{intent_id}-{register}-v1")
            rng.shuffle(combos)
            accepted = 0
            for text in combos:
                if accepted >= wanted:
                    break
                if key(text) in seen:
                    continue
                seen.add(key(text))
                cases.append(
                    {
                        "id": f"g-{intent_id}-{register}-{accepted + 1:03d}",
                        "kind": "intent",
                        "intent": intent_id,
                        "register": register,
                        "source": "generated",
                        "text": text,
                    }
                )
                accepted += 1
                made += 1
            if accepted < wanted:
                raise SystemExit(
                    f"{intent_id}/{register}: only {accepted}/{wanted} unique generated cases "
                    f"(add phrases or frames)"
                )
        per_intent[intent_id] = made
    return cases


def generate_gibberish(rng: random.Random, vocabulary: set[str], count: int) -> list[str]:
    out: list[str] = []
    attempts = 0
    while len(out) < count and attempts < count * 50:
        attempts += 1
        words = [pseudo_word(rng) for _ in range(rng.randint(2, 4))]
        if any(word in vocabulary for word in words):
            continue
        text = " ".join(words)
        if rng.random() < 0.25:
            text += " " + rng.choice(["pls", "please", "now"])
        out.append(text)
    return out


def generate_symbols(rng: random.Random, count: int) -> list[str]:
    """Digit strings, prices, times, emoji runs, punctuation and URLs."""
    candidates: list[str] = []
    for _ in range(count * 4):
        digits = "".join(rng.choice(string.digits) for _ in range(rng.randint(3, 12)))
        kind = rng.randrange(8)
        if kind == 0:
            candidates.append(digits)
        elif kind == 1:
            candidates.append(" ".join(rng.choice(EMOJI) for _ in range(rng.randint(2, 4))))
        elif kind == 2:
            candidates.append("".join(rng.choice("?!.,;:-_#@$%^&*()") for _ in range(rng.randint(3, 10))))
        elif kind == 3:
            candidates.append(rng.choice([f"{digits} please", f"tel {digits}",
                                          f"{digits[:2]}-{digits[2:]}", f"gate {digits[:2]}",
                                          f"flight 6e{digits[:3]}", f"row {digits[:2]}"]))
        elif kind == 4:
            candidates.append(rng.choice([f"${digits[:3]}", f"¥{digits[:4]}", f"€{digits[:3]}.{digits[:2]}",
                                          f"{digits[:2]}:{digits[2:4]}pm", f"{digits[:2]} hours"]))
        elif kind == 5:
            candidates.append(rng.choice(["#soralink", "@jal", "www.soralink.app",
                                          "http://.com", "+91-", "xx@yy"]))
        elif kind == 6:
            candidates.append(rng.choice(["?????", "!!!!!", "%%%%%", ".....*****"]))
        else:
            candidates.append(rng.choice(["abc123", "123abc", "0.5", "14:30", "B12",
                                          "2026-10-25", "3/4", "12a 12b"]))
    out: list[str] = []
    for value in candidates:
        if value not in out:
            out.append(value)
        if len(out) >= count:
            break
    if len(out) < count:
        raise SystemExit(f"symbol pool too small: {len(out)} < {count}")
    return out


def generate_wrong_script(count: int) -> list[str]:
    variants: list[str] = []
    for phrases in WRONG_SCRIPT.values():
        for phrase in phrases:
            variants.extend(
                [phrase, f"{phrase}?", f"{phrase}？", f"{phrase} {phrase}", f"… {phrase}"]
            )
    if len(variants) < count:
        raise SystemExit(f"wrong-script pool too small: {len(variants)} < {count}")
    return variants  # dedupe happens downstream, so return the full candidate pool


def generate_ood(rng: random.Random, count: int | None = None) -> list[str]:
    combos = [template.format(t=topic) for template in OOD_TEMPLATES for topic in OOD_TOPICS]
    rng.shuffle(combos)
    return combos[:count] if count else combos


def generate_degenerate(rng: random.Random, count: int) -> list[str]:
    cobbles = [" ".join(pair) for pair in itertools.permutations(FILLERS, 2)]
    rng.shuffle(cobbles)
    return FILLERS + cobbles


def generate_failure_cases(seen: set[str], vocabulary: set[str]) -> list[dict]:
    rng = random.Random(4242)
    #: category -> (generated candidates, how many must survive dedupe)
    plan: list[tuple[str, list[str], int]] = [
        ("gibberish", generate_gibberish(rng, vocabulary, 700), 500),
        ("symbols", generate_symbols(rng, 120), 120),
        ("wrong_script", generate_wrong_script(250), 250),
        ("out_of_domain", generate_ood(rng, None), 960),
        ("statement", STATEMENTS, 40),
        ("degenerate", generate_degenerate(rng, 80), 80),
    ]
    cases: list[dict] = []
    shortfalls: list[str] = []

    for category, candidates, wanted in plan:
        added = 0
        for text in candidates:
            if added >= wanted:
                break
            text = clean(text)
            if not text or key(text) in seen:
                continue
            seen.add(key(text))
            added += 1
            cases.append(
                {
                    "id": f"fg-{category[:6]}-{len(cases) + 1:04d}",
                    "kind": "failure",
                    "category": category,
                    "source": "generated",
                    "text": text,
                }
            )
        if added < wanted:
            shortfalls.append(f"{category}: {added}/{wanted}")

    if shortfalls:
        raise SystemExit(
            "failure blocks came up short (add candidates or topics): " + ", ".join(shortfalls)
        )
    return cases


def write_suite(suite: dict, cases: list[dict]) -> None:
    head = {key_name: value for key_name, value in suite.items() if key_name != "cases"}
    head["total_cases"] = len(cases)
    head["generated"] = sum(1 for case in cases if case.get("source") == "generated")
    text = json.dumps(head, indent=2, ensure_ascii=False)
    text = text[:-2]  # drop closing "\n}"
    body = ",\n".join("    " + json.dumps(case, ensure_ascii=False) for case in cases)
    SUITE_PATH.write_text(f'{text},\n  "cases": [\n{body}\n  ]\n}}\n', encoding="utf-8")


def main() -> int:
    suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    curated = [case for case in suite["cases"] if case.get("source") != "generated"]
    for case in curated:
        case.setdefault("source", "curated")

    seen = {key(case["text"]) for case in curated} | load_training_texts()
    vocabulary = load_catalog_vocabulary()

    generated_intent = generate_intent_cases(seen, target_extra=TARGET_INTENT_GENERATED - 3540)
    generated_failure = generate_failure_cases(seen, vocabulary)
    cases = curated + generated_intent + generated_failure

    if len(generated_intent) != TARGET_INTENT_GENERATED:
        raise SystemExit(f"intent generated {len(generated_intent)} != {TARGET_INTENT_GENERATED}")
    if len(generated_failure) != TARGET_FAILURE_GENERATED:
        raise SystemExit(f"failure generated {len(generated_failure)} != {TARGET_FAILURE_GENERATED}")
    if len(cases) != TARGET_TOTAL:
        raise SystemExit(f"suite has {len(cases)} cases, expected {TARGET_TOTAL}")
    if len({key(case["text"]) for case in cases}) != len(cases):
        raise SystemExit("duplicate texts in suite")

    write_suite(suite, cases)
    curated_intent = sum(1 for case in cases if case["kind"] == "intent" and case["source"] == "curated")
    curated_failure = sum(1 for case in cases if case["kind"] == "failure" and case["source"] == "curated")
    print(f"[suite] {len(cases)} cases -> {SUITE_PATH}")
    print(f"[suite] intent {curated_intent} curated + {len(generated_intent)} generated")
    print(f"[suite] failure {curated_failure} curated + {len(generated_failure)} generated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
