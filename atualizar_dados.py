"""
Atualiza os dados do painel 3D (index.html) a partir da planilha CSV.

Uso (no terminal, na pasta onde estão os dois arquivos):
    python atualizar_dados.py planilha.csv index.html index_novo.html

Precisa de Python 3 e da biblioteca pandas (pip install pandas).
A planilha precisa ter as colunas: id_beneficiario, id_turma, nucleo_familiar,
municipio, valor_inicial (ex.: "R$ 810,50") e referencia (ex.: 01/10/2026).
"""
import re, sys, json
import pandas as pd

if len(sys.argv) != 4:
    sys.exit(__doc__)
CSV, SRC, OUT = sys.argv[1:4]

html = open(SRC, encoding="utf-8").read()
m = re.search(r"var DATA=(\{.*?\});\n", html, re.S)
if not m:
    sys.exit("Não encontrei o bloco 'var DATA=' no HTML.")
D = json.loads(m.group(1))          # mantém o mapa (feats) e o resto como está

# ---------- 1. Limpeza ----------
df = pd.read_csv(CSV, dtype=str)
df["mun"] = (df.municipio.str.strip()
               .str.replace(r"-MA$", "", regex=True).str.strip()
               .replace({"Olinda Nova": "Olinda Nova do Maranhão"}))
df["v"] = (df.valor_inicial.str.replace("R$", "", regex=False)
             .str.replace(".", "", regex=False)
             .str.replace(",", ".", regex=False).str.strip().astype(float))
df["m"] = pd.to_datetime(df.referencia, format="%d/%m/%Y").dt.strftime("%Y-%m")
df["nuc"] = df.nucleo_familiar.astype(int)

dup = df.duplicated(["id_beneficiario", "referencia"]).sum()
if dup:
    sys.exit(f"Há {dup} linhas repetidas (mesmo beneficiário no mesmo mês). Corrija a planilha.")
sem_mapa = sorted(set(df.mun) - set(D["data"]) - {f["n"] for f in D["feats"]})
if sem_mapa:
    sys.exit(f"Municípios que não existem no mapa: {sem_mapa}")

# ---------- 2. Meses e turmas ----------
months = pd.period_range(df.m.min(), df.m.max(), freq="M").strftime("%Y-%m").tolist()
def tkey(t):
    mm, yy = t[2:].split("/"); return (int(yy), int(mm))
turmas = sorted(df.id_turma.unique(), key=tkey)

def cum(sub, mo):
    x = sub[sub.m <= mo]
    return [int(x.id_beneficiario.nunique()), int(x.nuc.nunique()),
            round(float(x.v.sum()), 2), int(len(x))]

total = [cum(df, mo) for mo in months]
data = {mu: [cum(g, mo) for mo in months] for mu, g in df.groupby("mun")}

# ---------- 3. Núcleos (uma casa por núcleo) ----------
first = df.groupby("nuc").agg(e=("m", "min"),
                              t=("id_turma", lambda x: min(x, key=tkey))).reset_index()
usadas = set(first.t)
vazias = [t for t in turmas if t not in usadas]
turmas = [t for t in turmas if t in usadas]          # rua sem casa não entra
first["ei"] = first.e.map({mo: i for i, mo in enumerate(months)})
first["ti"] = first.t.map({t: i for i, t in enumerate(turmas)})
first = first.sort_values(["ei", "ti", "nuc"]).reset_index(drop=True)

nuc = []
for i, r in first.iterrows():
    g = df[df.nuc == r.nuc]
    b, p, v = [], [], []
    for mo in months:
        x = g[g.m <= mo]
        b.append(int(x.id_beneficiario.nunique())); p.append(int(len(x)))
        v.append(round(float(x.v.sum()), 2))
    nuc.append({"t": int(r.ti), "e": int(r.ei), "b": b, "p": p, "v": v, "n": i + 1})

# ---------- 3b. Ativos x que deixaram o programa ----------
# ativo no mês  = recebeu parcela naquele mês
# deixou        = já recebeu antes, mas o último pagamento foi em mês anterior
ult = df.groupby("id_beneficiario").m.max()
act = []
for mo in months:
    ativos = int(df[df.m == mo].id_beneficiario.nunique())
    saiu = int((ult < mo).sum())
    act.append([ativos, saiu])

D.update(months=months, total=total, data=data, turmas=turmas, nuc=nuc, act=act)
novo = "var DATA=" + json.dumps(D, ensure_ascii=False, separators=(",", ":")) + ";\n"
html = html[:m.start()] + novo + html[m.end():]

# ---------- 4. Frase de rodapé com os totais ----------
MESES = ["janeiro","fevereiro","março","abril","maio","junho","julho","agosto",
         "setembro","outubro","novembro","dezembro"]
ano, mes = months[-1].split("-")
b_, n_, v_, p_ = total[-1]
valor = f"{v_:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
frase = (f"Base tratada (nomes de municípios padronizados, valores e datas convertidos): "
         f"em {MESES[int(mes)-1]} de {ano}, {b_} vidas, {n_} núcleos, R$ {valor} e {p_} parcelas.")
html = re.sub(r"Base tratada \(nomes.*?parcelas\.", lambda _: frase, html, count=1, flags=re.S)

open(OUT, "w", encoding="utf-8").write(html)
print("Pronto:", OUT)
print("Ativos / deixaram no último mês:", act[-1])
print("Último mês:", months[-1], "| vidas", b_, "| núcleos", n_, "| R$", valor, "| parcelas", p_)
print("Ruas (turmas):", len(turmas), "| ruas vazias ignoradas:", vazias or "nenhuma")
