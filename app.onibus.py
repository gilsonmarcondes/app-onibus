import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
import json
import gzip
from streamlit_geolocation import streamlit_geolocation # 1. A nova biblioteca de GPS

st.set_page_config(page_title="Monitor SPTrans - Gilson", layout="centered")

st.title("🚌 Monitor de Frota SPTrans")

TOKEN = '0ff07fb8ed51fd939f51e92b03571a51fb72aad64fc19586909fd97ac1b6091a'

@st.cache_data
def carregar_gtfs():
    try:
        with gzip.open('trajetos.json.gz', 'rt', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Erro ao carregar trajetos oficiais: {e}")
        return {}

trajetos_sp = carregar_gtfs()

# --- 2. O BOTÃO DE LOCALIZAÇÃO ---
st.write("📍 **Onde estou agora?**")
localizacao = streamlit_geolocation()

# Definimos a posição padrão (Sabesp) caso o utilizador não ative o GPS
minha_lat, minha_lon = -23.6331, -46.7028
zoom_mapa = 13

if localizacao and localizacao.get('latitude') and localizacao.get('longitude'):
    minha_lat = localizacao['latitude']
    minha_lon = localizacao['longitude']
    zoom_mapa = 15 # Fazemos um zoom maior porque sabemos exatamente onde está
    st.success("Localização capturada com sucesso!")

st.divider() # Uma linha visual para separar a pesquisa

linha_busca = st.text_input("Digite o número da linha (ex: 7550, 6500):", value="7550")

if linha_busca:
    session = requests.Session()
    session.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN}")
    
    linhas = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={linha_busca}").json()
    
    if linhas:
        opcoes = {}
        dados_das_linhas = {}
        
        for l in linhas:
            if l.get('sl') == 1:
                trajeto = f"{l.get('tp', '')} ➔ {l.get('ts', '')}"
            else:
                trajeto = f"{l.get('ts', '')} ➔ {l.get('tp', '')}"
            
            nome_linha = f"{l.get('lt', 'Linha')} - {l.get('tl', '')} | {trajeto}"
            opcoes[nome_linha] = l['cl']
            dados_das_linhas[nome_linha] = l
        
        escolha = st.selectbox("Escolha o sentido desejado:", list(opcoes.keys()))
        id_linha = opcoes[escolha]
        linha_selecionada = dados_das_linhas[escolha]

        frota = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={id_linha}").json()

        st.subheader(f"Localização Real - {escolha}")
        
        # 3. CENTRAR O MAPA NA SUA POSIÇÃO
        m = folium.Map(location=[minha_lat, minha_lon], zoom_start=zoom_mapa, tiles='CartoDB positron')

        # 4. ADICIONAR O MARCADOR DO UTILIZADOR
        if localizacao and localizacao.get('latitude'):
            folium.Marker(
                [minha_lat, minha_lon],
                popup="Você está aqui",
                icon=folium.Icon(color='green', icon='user', prefix='fa')
            ).add_to(m)

        # Desenha a linha vermelha do trajeto
        chave_gtfs = f"{linha_selecionada.get('lt')}-{linha_selecionada.get('tl')}-{linha_selecionada.get('sl')}"
        
        if chave_gtfs in trajetos_sp:
            coordenadas_oficiais = trajetos_sp[chave_gtfs]
            folium.PolyLine(
                coordenadas_oficiais,
                color="#FF0000",
                weight=4,
                opacity=0.7,
                tooltip="Trajeto Oficial (GTFS)"
            ).add_to(m)
        else:
            st.warning("Trajeto oficial não encontrado. Mostrando apenas os autocarros.")

        # Adiciona os autocarros no mapa
        if frota and 'vs' in frota and frota['vs']:
            for v in frota['vs']:
                folium.Marker(
                    [v['py'], v['px']],
                    popup=f"Prefixo: {v['p']}",
                    icon=folium.Icon(color='blue', icon='bus', prefix='fa')
                ).add_to(m)
            st.success(f"Encontrados {len(frota['vs'])} autocarros em circulação.")
        else:
            st.warning("Nenhum autocarro desta linha localizado neste sentido agora.")

        # Exibe o mapa
        st_folium(m, width=700, height=500, returned_objects=[])
        
        if st.button('🔄 Atualizar Posição dos Autocarros'):
            st.rerun()
    else:
        st.error("Linha não encontrada. Tente apenas os números.")