"""Build the bounded final A1 course from the preserved proposal, never from benchmarks."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "cross_demo/docs/curso_demo/propuesta_curso.md"


def plain(text):
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    return text.replace("**", "").replace("~~", "").replace("`", "").replace("*", "").strip()


def blocks(section):
    # The course uses the actual learner lessons, not the tutor demonstration walkthrough.
    section = section.split("#### Secuencia de práctica")[0]
    result, paragraph = [], []

    def flush():
        if paragraph:
            result.append({"kind": "paragraph", "text": plain(" ".join(paragraph)), "rows": []})
            paragraph.clear()

    lines = section.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line == "---":
            flush()
        elif line.startswith("#### "):
            flush()
            result.append({"kind": "heading", "text": plain(line[5:]), "rows": []})
        elif line.startswith("|"):
            flush()
            rows = []
            while True:
                if not re.match(r"^\|[\s:|\-]+\|$", line):
                    rows.append([plain(x) for x in line.strip("|").split("|")])
                if i == len(lines) or not lines[i].strip().startswith("|"):
                    break
                line = lines[i].strip()
                i += 1
            result.append({"kind": "table", "text": "", "rows": rows})
        elif line.startswith(">"):
            flush()
            result.append({"kind": "example", "text": plain(line.lstrip("> ")), "rows": []})
        elif re.match(r"^(?:[-+] |\d+\. )", line):
            flush()
            result.append({"kind": "bullet", "text": plain(re.sub(r"^(?:[-+] |\d+\. )", "", line)), "rows": []})
        else:
            paragraph.append(line)
    flush()
    return result


def main():
    source = SOURCE.read_text(encoding="utf-8")
    original = source
    # Editorial corrections are applied to this derived asset, not to the supplied proposal.
    source = source.replace("En inglés, toda oración necesita un sujeto explícito", "En estas oraciones declarativas en inglés usamos un sujeto explícito")
    source = source.replace("la edad siempre se expresa con *to be*", "para indicar la edad de una persona usamos normalmente *to be*")
    source = source.replace("sonido vocálico (*a, e, i, o, u*)", "sonido vocálico (la elección depende del sonido, no solo de la letra)")
    source = source.replace("van **antes** del verbo principal", "suelen ir **antes** del verbo principal")
    source = source.replace('(*"I **always** eat breakfast at home"*, nunca *"I eat always"*)', '(*"I **always** eat breakfast at home"* es el orden neutro que practicamos aquí)')
    data = json.loads(re.search(r"```json\s*(.*?)```", source, re.S).group(1))
    meta = [
        ("Presentarte en inglés", "Introducing yourself", "Tu nombre, tu origen y lo que haces. Escribe tu primera presentación.", "ABOUT ME", 20),
        ("Contar tu rutina", "My daily routine", "Habla de tus hábitos, tus horarios y las pequeñas cosas de cada día.", "EVERY DAY", 25),
        ("Describir tu hogar", "My home & messages", "Describe tu espacio y escribe un mensaje para invitar a alguien.", "MY PLACE", 20),
    ]
    sections = re.split(r"### Unidad \d+[^\n]*\n", source)[1:4]
    units = []
    for unit, section, (title, subtitle, summary, label, minutes) in zip(data["units"], sections, meta, strict=True):
        activities = unit["activities"]
        for activity in activities:
            # Remove a potentially grammatical, marked-order distractor. This item now tests agreement.
            if activity["id"] == "u02-opcion-03":
                activity["options"][0]["text"] = "I always eats breakfast at home."
                activity["explanation"] = "Con I usamos eat, sin -s. I always eat breakfast at home usa el orden habitual del adverbio de frecuencia."
            if activity["id"] == "u03-opcion-03":
                activity["options"][2]["text"] = "Is there are a balcony in your apartment?"
                activity["explanation"] = "Para esta pregunta con a balcony (singular), usamos Is there a balcony...? No combinamos is y are."
        units.append(dict(id=unit["id"], title=title, subtitle=subtitle, summary=summary, label=label,
                          minutes=minutes, lessons=blocks(section), activities=activities))
    output = dict(id="writing-local-a1", version="1.0.0", title="Inglés para tu día a día", level="A1",
                  source_sha256=hashlib.sha256(original.encode()).hexdigest(), units=units)
    path = ROOT / "Course.Core/Assets/course-a1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Built {len(units)} units, {sum(len(u['activities']) for u in units)} activities; learner lessons retained.")


if __name__ == "__main__":
    main()
