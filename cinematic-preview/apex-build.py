"""Build a separate, static APEX preview; never edits the existing index.html."""
from pathlib import Path
import re
root = Path(__file__).resolve().parent
base = (root / 'index.html').read_text(encoding='utf-8')
assert 'data-film="hero"' in base and 'id="vehicle-brands"' in base, 'Unexpected base: use the licensed-model studio edition.'
assert '<script type="module" src="film.js"></script>' in base
hero = '''<section id="drive" class="drive film-section" data-film="hero" aria-label="CHECK92 — Beyond stock"><div class="film-sticky"><div class="apex-hero-top"><span class="apex-eyebrow">CHECK92 / AUTOMOTIVE ENGINEERING</span><h1>BEYOND<span>STOCK.</span></h1></div><div class="apex-hero-bottom"><div><span class="apex-eyebrow">СЕВАСТОПОЛЬ · ЧИП-ТЮНИНГ И ЭЛЕКТРОНИКА</span><p>Не просто больше мощности.<br>Больше характера.</p></div><a href="#start" class="apex-enter">ЗАГЛЯНУТЬ ВНУТРЬ <span>↗</span></a></div><div class="apex-scene-code" aria-hidden="true">01 / THE MACHINE</div></div></section>'''
base,n = re.subn(r'<section id="drive".*?</section>', lambda _:hero, base, count=1, flags=re.S)
assert n == 1
circuit = '''<section id="circuit" class="film-section apex-circuit" data-film="circuit" aria-labelledby="circuit-title"><div class="film-sticky"><div class="film-copy"><span class="apex-eyebrow">03 / INSIDE THE CODE</span><h2 id="circuit-title">Характер<br>начинается<br><em>с кода.</em></h2><p>От сигнала на входе — к решению внутри блока. Работаем с программой, которая управляет механикой.</p></div><div class="apex-caption"><span>СИГНАЛ → АЛГОРИТМ → ОТКЛИК</span><span>Художественная визуализация</span></div></div></section>'''
response = '''<section id="response" class="film-section apex-response" data-film="response" aria-labelledby="response-title"><div class="film-sticky"><div class="film-copy"><span class="apex-eyebrow">06 / THE RESPONSE</span><h2 id="response-title">Чувствуется.<br><em>Не обещается.</em></h2><p>Результат определяют автомобиль, диагностика и настройка. Не универсальная цифра из рекламы.</p></div><div class="apex-graph" role="img" aria-label="Иллюстративная схема изменения отклика. Не замер мощности."><div class="apex-graph-head"><span>RESPONSE / SCHEMATIC</span><span class="apex-orange">● SIGNAL</span></div><svg viewBox="0 0 540 220" fill="none" aria-hidden="true"><path class="apex-grid" d="M20 20V195H520 M20 65H520 M20 110H520 M20 155H520 M120 20V195 M220 20V195 M320 20V195 M420 20V195"/><path class="apex-reference" d="M20 183C100 180 129 165 183 140S265 94 327 72S443 50 520 46"/><path id="response-line" d="M20 183C100 180 114 146 174 110S259 60 332 38S455 32 520 26"/></svg><div class="apex-graph-foot"><span>INPUT</span><span>Иллюстрация, не график замера</span><span>OUTPUT</span></div></div><div class="apex-caption"><span>МЕХАНИКА × ПРОГРАММА</span><a href="#platform">Подобрать автомобиль ↗</a></div></div></section>'''
velocity = '''<section id="velocity" class="film-section apex-velocity" data-film="velocity" aria-labelledby="velocity-title"><div class="film-sticky"><div class="apex-velocity-title"><span class="apex-eyebrow">08 / YOUR NEXT MOVE</span><h2 id="velocity-title">DRIVE<br><em>DIFFERENT.</em></h2></div><div class="apex-caption"><span>ТВОЙ АВТОМОБИЛЬ. ТВОЯ ЗАДАЧА.</span><a class="apex-enter" href="#contact">НАЧНЁМ С ТВОЕЙ МАШИНЫ ↗</a></div></div></section>'''
base=base.replace('<div class="manifesto">',circuit+'\n<div class="manifesto">',1)
base=base.replace('<section class="section platform"',response+'\n<section class="section platform"',1)
base=base.replace('<section class="section contact"',velocity+'\n<section class="section contact"',1)
base=base.replace('<body>','<body class="apex">',1)
base=re.sub(r'<title>.*?</title>','<title>CHECK92 — APEX / Beyond stock</title>',base,count=1)
base=base.replace('</head>','<meta name="robots" content="noindex"><link rel="stylesheet" href="apex.css"></head>',1)
base=base.replace('<script type="module" src="film.js"></script>','<script type="module" src="apex.bundle.js"></script>',1)
rail='''<nav class="apex-chapters" aria-label="Разделы истории"><a href="#drive" data-chapter="hero"><i></i><span>Автомобиль</span></a><a href="#start" data-chapter="ecu"><i></i><span>Электроника</span></a><a href="#circuit" data-chapter="circuit"><i></i><span>Код</span></a><a href="#services" data-chapter="services"><i></i><span>Механика</span></a><a href="#response" data-chapter="response"><i></i><span>Отклик</span></a><a href="#velocity" data-chapter="velocity"><i></i><span>Движение</span></a></nav><div class="apex-progress" aria-hidden="true"><span></span></div>'''
base=base.replace('</body>',rail+'</body>',1)
assert all(base.count('id="'+s+'"')==1 for s in ['circuit','response','velocity','start','platform','form'])
assert 'src="film.js"' not in base
(root/'apex.html').write_text(base,encoding='utf-8')
print('APEX static preview built; original index.html unchanged.')
