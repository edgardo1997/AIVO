"""Generate INFORME_18_FASES.md from all FASE reports."""

import re
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "INFORME_18_FASES.md"

files = {}
# root FASE*_REPORT.md for phases 3-17
for p in ROOT.glob("FASE*_REPORT.md"):
    m = re.search(r"FASE(\d+)_REPORT", p.name)
    if m:
        files[int(m.group(1))] = p
# docs/intelligence_migration for missing early phases (0, 1, 2)
for p in (ROOT / "docs" / "intelligence_migration").glob("FASE_*.md"):
    m = re.search(r"FASE_(\d+)_", p.name)
    if m and int(m.group(1)) <= 2 and int(m.group(1)) not in files:
        files[int(m.group(1))] = p

phase_rows = []

for phase_num, p in files.items():
    text = p.read_text(encoding="utf-8", errors="ignore")
    # title from first heading
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else p.stem
    # find verdict: first bold state after the "Veredicto"/"Conclusion"/"Decisión" section
    verdict = "(estado no encontrado)"
    m = re.search(r"(?i)(^#+\s+.*(?:veredicto|conclusi[oó]n|decisi[oó]n|resultado final).*?)\s*\n(.*)", text, re.MULTILINE | re.DOTALL)
    rest = m.group(2) if m else text
    for line in rest.splitlines():
        b = re.search(r"\*\*([^*]+?)\*\*", line)
        if b and re.match(r"(COMPLETADO|PARCIAL|BLOQUEAD[OA]?|RECHAZADO|NO-GO|GO)\b", b.group(1)):
            state_word = re.match(r"(COMPLETADO|PARCIAL|BLOQUEAD[OA]?|RECHAZADO|NO-GO|GO)", b.group(1)).group(1)
            verdict = f"**{state_word}**"
            break

    # fallback: last bold state anywhere in the file
    if verdict == "(estado no encontrado)":
        for m in re.finditer(r"\*\*([^*]+?)\*\*", text):
            inner = m.group(1)
            if re.match(r"(COMPLETADO|PARCIAL|BLOQUEAD[OA]?|RECHAZADO|NO-GO|GO)\b", inner):
                state_word = re.match(r"(COMPLETADO|PARCIAL|BLOQUEAD[OA]?|RECHAZADO|NO-GO|GO)", inner).group(1)
                verdict = f"**{state_word}**"
    # extract main finding: first table row with P0/P1/P2 or a block item
    finding = "—"
    m = re.search(r"\|\s*([A-Z]{2,}-\d+)\s*\|\s*[^|]+\|\s*(P[0-4])\s*\|\s*([^|]+)\|", text)
    if m:
        finding = f"{m.group(1)} ({m.group(2)}): {m.group(3).strip()}"
    else:
        for line in text.splitlines():
            if re.search(r"P[0-4]", line) and re.search(r"[A-Z]{2,}-\d+", line):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 3:
                    finding = " | ".join(parts[:3])
                else:
                    finding = line.strip()
                break
    phase_rows.append((phase_num, title, verdict, finding))

phase_rows.sort(key=lambda x: x[0])

with OUT.open("w", encoding="utf-8") as f:
    f.write("# Informe de las 18 Fases de Sentinel\n\n")
    f.write("Fecha: 2026-08-05\n")
    f.write("Repositorio: `C:\\Users\\edgar\\OneDrive\\Documents\\AIVO`\n")
    f.write("Rama: `main`\n\n")
    f.write("## Resumen por fase\n\n")
    f.write("| Fase | Título | Estado/Veredicto | Hallazgo clave |\n")
    f.write("| ---- | ------ | ---------------- | --------------- |\n")
    for phase_num, title, verdict, finding in phase_rows:
        f.write(f"| FASE {phase_num} | {title} | {verdict} | {finding} |\n")
    if 1 not in {row[0] for row in phase_rows}:
        f.write("| FASE 1 | (reporte no encontrado en el repositorio) | — | — |\n")
    f.write("\n## Conclusiones generales\n\n")
    f.write("- Fases 0–2: fase inicial y protección arquitectónica.\n")
    f.write("- Fases 3–5: estabilidad, pruebas y firmas de canales.\n")
    f.write("- Fase 6–8: firmas, canales, UX simplificada.\n")
    f.write("- Fases 9–14: validación de flujos, lifecycle, persistencia, instalación, rendimiento, soporte.\n")
    f.write("- Fase 15–17: programas Alpha. Ninguna fue aprobada para continuar.\n")
    f.write("\n## Bloqueos actuales\n\n")
    f.write("- FASE 9: no se validaron flujos principales desde GUI real.\n")
    f.write("- FASE 10: segunda instancia permitida.\n")
    f.write("- FASE 11: `StorageEngine.close()` puede dejar hilo activo.\n")
    f.write("- FASE 12: instalación no validada en entorno limpio real; desinstalación deja residuales.\n")
    f.write("- FASE 14: no existe diagnóstico exportable ni Build ID visible.\n")
    f.write("- FASE 15: NO-GO. FASE 16: BLOQUEADA. FASE 17: BLOQUEADO POR FASE ANTERIOR.\n")
    f.write("\n## Recomendación\n\n")
    f.write("No avanzar a Alpha interna, cerrada ni externa hasta cerrar P1 y completar FASE9, FASE10, FASE11, FASE12 y FASE14.\n")

print(f"Written {OUT}")
