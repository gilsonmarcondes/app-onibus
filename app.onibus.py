import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
import json
import gzip
from streamlit_geolocation import streamlit_geolocation
import googlemaps # Nova biblioteca do Google

st.set_page_config(page_title="Monitor SPTrans - Gilson", layout="centered")

st.title("🚌 Roteirizador SPTrans")

# --- CHAVES DE ACESSO ---
TOKEN_SPTRANS = '0ff07fb8ed51fd939f51e92b03571a51fb72aad64fc19586909fd97ac1b6091a'
CHAVE_GOOGLE = 'AIzaSyAtp5jarrnwyy3_JWVfoWGbKlfEd4NjSKk' # Cole a sua chave aqui

# Inicializa o cliente do Google
gmaps = googlemaps.Client(key=CHAVE_GOOGLE)

@st.cache_data
def carregar_gtfs():
    try:
        with gzip.open('trajetos.json.gz', 'rt', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

trajetos_sp = carregar_gtfs()

st.write("📍 **1. Onde estou agora?**")
localizacao = streamlit_geolocation()

minha_lat, minha_lon = -23.6331, -46.7028
zoom_mapa = 13

if localizacao and localizacao.get('latitude'):
    minha_lat = localizacao['latitude']
    minha_lon = localizacao['longitude']
    zoom_mapa = 15
    st.success("Localização capturada!")

st.divider()

# --- A NOVA FUNÇÃO: PARA ONDE VAMOS? ---
st.write("🎯 **2. Para onde quer ir?**")
destino = st.text_input("Ex: Avenida Paulista, 1000", placeholder="Digite o endereço ou local")

if destino and localizacao and localizacao.get('latitude'):
    with st.spinner("A consultar as rotas do Google Maps..."):
        try:
            origem = (minha_lat, minha_lon)
            # Pede ao Google a rota de transportes públicos
            rotas = gmaps.directions(origem, destino, mode="transit", region="br")
            
            linhas_sugeridas = []
            
            if rotas:
                passos = rotas[0]['legs'][0]['steps']
                for passo in passos:
                    if passo['travel_mode'] == 'TRANSIT':
                        detalhes = passo['transit_details']
                        if detalhes['line']['vehicle']['type'] == 'BUS':
                            # O Google devolve o número da linha (ex: "7550-10")
                            linhas_sugeridas.append(detalhes['line']['short_name'])
                
                if linhas_sugeridas:
                    st.success(f"O Google sugere apanhar a linha: **{linhas_sugeridas[0]}**")
                    # Em vez do utilizador digitar, o Google preenche a busca automaticamente!
                    linha_busca = linhas_sugeridas[0].split('-')[0] # Pega só os números (ex: 7550)
                else:
                    st.warning("O Google não encontrou rotas diretas de autocarro para este destino.")
                    linha_busca = None
            else:
                st.error("Não foi possível traçar uma rota.")
                linha_busca = None
        except Exception as e:
            st.error(f"Erro ao consultar o Google: {e}")
            linha_busca = None
else:
    # Se não usar a rota, permite a busca manual clássica
    linha_busca = st.text_input("Ou procure uma linha manualmente (ex: 7550):")

# --- O CÓDIGO CLÁSSICO DA SPTRANS CONTINUA AQUI ---
if linha_busca:
    session = requests.Session()
    session.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
    
    linhas = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={linha_busca}").json()
    
    if linhas:
        opcoes = {}
        dados_das_linhas = {}
        for l in linhas:
            trajeto = f"{l.get('tp', '')} ➔ {l.get('ts', '')}" if l.get('sl') == 1 else f"{l.get('ts', '')} ➔ {l.get('tp', '')}"
            nome_linha = f"{l.get('lt', 'Linha')} - {l.get('tl', '')} | {trajeto}"
            opcoes[nome_linha] = l['cl']
            dados_das_linhas[nome_linha] = l
        
        escolha = st.selectbox("Escolha o sentido desejado:", list(opcoes.keys()))
        id_linha = opcoes[escolha]
        linha_selecionada = dados_das_linhas[escolha]

        frota = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={id_linha}").json()
        
        m = folium.Map(location=[minha_lat, minha_lon], zoom_start=zoom_mapa, tiles='CartoDB positron')

        # O seu marcador
        if localizacao and localizacao.get('latitude'):
            folium.Marker([minha_lat, minha_lon], popup="Você está aqui", icon=folium.Icon(color='green', icon='user', prefix='fa')).add_to(m)

        # O trajeto vermelho
        chave_gtfs = f"{linha_selecionada.get('lt')}-{linha_selecionada.get('tl')}-{linha_selecionada.get('sl')}"
        if chave_gtfs in trajetos_sp:
            folium.PolyLine(trajetos_sp[chave_gtfs], color="#FF0000", weight=4, opacity=0.7).add_to(m)

        # Os autocarros azuis
        if frota and 'vs' in frota and frota['vs']:
            for v in frota['vs']:
                folium.Marker([v['py'], v['px']], popup=f"Prefixo: {v['p']}", icon=folium.Icon(color='blue', icon='bus', prefix='fa')).add_to(m)
            st.success(f"Encontrados {len(frota['vs'])} autocarros em circulação.")
        
        st_folium(m, width=700, height=500, returned_objects=[])
        
        if st.button('🔄 Atualizar Posição dos Autocarros'):
            st.rerun()