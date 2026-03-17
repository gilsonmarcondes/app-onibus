import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
import json
import gzip
from streamlit_geolocation import streamlit_geolocation
import googlemaps

st.set_page_config(page_title="Monitor SPTrans - Gilson", layout="centered")

st.title("🚌 Roteirizador SPTrans")

# --- CHAVES DE ACESSO ---
TOKEN_SPTRANS = '0ff07fb8ed51fd939f51e92b03571a51fb72aad64fc19586909fd97ac1b6091a'
CHAVE_GOOGLE = 'AIzaSyAtp5jarrnwyy3_JWVfoWGbKlfEd4NjSKk' # <-- COLE A SUA CHAVE AQUI

# Inicializa o cliente do Google
gmaps = googlemaps.Client(key=CHAVE_GOOGLE)

# --- CARREGA O MAPA COMPACTADO ---
@st.cache_data
def carregar_gtfs():
    try:
        with gzip.open('trajetos.json.gz', 'rt', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Erro ao carregar trajetos oficiais: {e}")
        return {}

trajetos_sp = carregar_gtfs()

# --- 1. CAPTURA A SUA LOCALIZAÇÃO ---
st.write("📍 **1. Onde estou agora?**")
localizacao = streamlit_geolocation()

minha_lat, minha_lon = -23.6331, -46.7028 # Sabesp como padrão
zoom_mapa = 13

if localizacao and localizacao.get('latitude'):
    minha_lat = localizacao['latitude']
    minha_lon = localizacao['longitude']
    zoom_mapa = 15
    st.success("Localização capturada com sucesso!")

st.divider()

# --- 2. O ROTEIRIZADOR (GOOGLE MAPS) ---
st.write("🎯 **2. Para onde quer ir?**")
destino = st.text_input("Ex: Avenida Paulista, 1000", placeholder="Digite o endereço ou local")

linha_busca = None # Começa vazia

if destino and localizacao and localizacao.get('latitude'):
    with st.spinner("Consultando as opções no Google Maps..."):
        try:
            origem = (minha_lat, minha_lon)
            
            # Pede várias rotas alternativas ao Google
            rotas = gmaps.directions(origem, destino, mode="transit", region="br", alternatives=True)
            
            linhas_sugeridas = set() # Evita opções repetidas
            
            if rotas:
                for rota in rotas:
                    passos = rota['legs'][0]['steps']
                    for passo in passos:
                        if passo['travel_mode'] == 'TRANSIT':
                            detalhes = passo['transit_details']
                            # Pega apenas Ônibus
                            if detalhes['line']['vehicle']['type'] == 'BUS':
                                linhas_sugeridas.add(detalhes['line']['short_name'])
                
                if linhas_sugeridas:
                    lista_linhas = list(linhas_sugeridas)
                    st.success(f"Encontramos {len(lista_linhas)} opções de ônibus para o seu destino!")
                    
                    # Cria as bolinhas para você escolher a linha
                    linha_escolhida = st.radio("Escolha a linha para ver no mapa:", lista_linhas)
                    
                    # Corta o final (ex: "7550-10" vira "7550") para a SPTrans entender
                    linha_busca = linha_escolhida.split('-')[0]
                else:
                    st.warning("O Google não encontrou rotas diretas de ônibus para este destino.")
            else:
                st.error("Não foi possível traçar uma rota.")
        except Exception as e:
            st.error(f"Erro ao consultar o Google: {e}")

# --- 3. BUSCA MANUAL (Se não usar o roteirizador) ---
if not linha_busca:
    linha_busca = st.text_input("Ou procure uma linha manualmente (ex: 7550):")

# --- 4. O MONITOR EM TEMPO REAL (SPTRANS) ---
if linha_busca:
    session = requests.Session()
    # Autentica na SPTrans
    session.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
    
    # Busca detalhes da linha
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

        # Busca os ônibus na rua
        frota = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={id_linha}").json()

        st.subheader(f"Localização Real - {escolha}")
        
        # Cria o mapa centralizado em você
        m = folium.Map(location=[minha_lat, minha_lon], zoom_start=zoom_mapa, tiles='CartoDB positron')

        # Adiciona o seu marcador verde
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
            st.warning("Trajeto oficial não encontrado. Mostrando apenas os ônibus.")

        # Adiciona os ônibus azuis
        if frota and 'vs' in frota and frota['vs']:
            for v in frota['vs']:
                folium.Marker(
                    [v['py'], v['px']],
                    popup=f"Prefixo: {v['p']}",
                    icon=folium.Icon(color='blue', icon='bus', prefix='fa')
                ).add_to(m)
            st.success(f"Encontrados {len(frota['vs'])} ônibus em circulação.")
        else:
            st.warning("Nenhum ônibus desta linha localizado neste sentido agora.")

        # Exibe o mapa na tela
        st_folium(m, width=700, height=500, returned_objects=[])
        
        if st.button('🔄 Atualizar Posição dos Ônibus'):
            st.rerun()
    else:
        st.error("Linha não encontrada na SPTrans.")