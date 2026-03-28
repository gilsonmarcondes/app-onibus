import pandas as pd
import json

print("A ler o ficheiro stops.txt da SPTrans...")

# Lê o ficheiro original
df_stops = pd.read_csv("stops.txt", dtype=str)

# Limpa e formata os dados
paradas_limpas = []
for index, row in df_stops.iterrows():
    paradas_limpas.append({
        "cp": row["stop_id"],
        "np": row["stop_name"],
        "py": float(row["stop_lat"]),
        "px": float(row["stop_lon"])
    })

# Guarda o novo ficheiro otimizado
with open("paradas.json", "w", encoding="utf-8") as f:
    json.dump(paradas_limpas, f, ensure_ascii=False)

print(f"Sucesso! paradas.json criado com {len(paradas_limpas)} paragens.")
