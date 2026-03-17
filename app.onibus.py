import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
import json
import gzip
from streamlit_geolocation import streamlit_geolocation
import googlemaps
import polyline

st.set_page_config(page_title="Monitor SPTrans - Gilson", layout="wide")

st.title("🗺️ Roteirizador Multimodal SPTrans")

# --- CHAVES DE ACESSO ---
TOKEN_SPTRANS = '0ff07fb8ed51fd939f51e92b03571a51fb72aad64fc19586909fd97ac1b6091a'
CHAVE_GOOGLE = 'AIzaSyAtp5jarrnwyy3_JWVfoWGbKlfEd4NjSKk' # <-- SUA CHAVE AQUI

gmaps = googlemaps.Client(key=CHAVE_GOOGLE)

@st.cache_data
def carregar_gtfs():
    try:
        with gzip.open('trajetos.json.gz', 'rt', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}
trajetos_sp = carregar_gtfs()

col1, col2 = st.columns([1, 2])

with col1:
    # --- 1. A NOVA LÓGICA DE ORIGEM (GPS ou TEXTO) ---
    st.write("📍 **1. De onde você vai sair?**")
    
    # O botão de GPS continua disponível
    localizacao = streamlit_geolocation()
    
    # O novo campo para digitar o endereço
    origem_digitada = st.text_input("Ou digite o endereço de partida:", placeholder="Ex: Terminal Bandeira ou UNESP")
    
    st.write("🎯 **2. Para onde quer ir?**")
    destino = st.text_input("Destino:", placeholder="Ex: Avenida Paulista, 1000")
    
    # Variáveis padrão
    origem_final = None
    minha_lat, minha_lon = -23.6331, -46.7028
    zoom_mapa = 13
    
    # O CÉREBRO DA ORIGEM: Decide se usa o texto ou o GPS
    if origem_digitada:
        origem_final = origem_digitada
        # Pede pro Google converter o texto em coordenadas para centrar o mapa certinho
        try:
            geo = gmaps.geocode(origem_digitada)
            if geo:
                minha_lat = geo[0]['geometry']['location']['lat']
                minha_lon = geo[0]['geometry']['location']['lng']
                zoom_mapa = 15
        except:
            pass
    elif localizacao and localizacao.get('latitude'):
        minha_lat = localizacao['latitude']
        minha_lon = localizacao['longitude']
        origem_final = (minha_lat, minha_lon)
        zoom_mapa = 15
        st.success("📍 GPS Ativo!")
    
    rota_selecionada = None
    linhas_para_buscar = []

    # --- 2. O ROTEIRIZADOR ---
    if origem_final and destino:
        with st.spinner("Analisando as melhores rotas..."):
            try:
                # Agora ele manda a origem_final (que pode ser texto ou GPS) pro Google
                rotas = gmaps.directions(origem_final, destino, mode="transit", region="br", alternatives=True)
                
                if rotas:
                    opcoes_rotas = {}
                    
                    for i, rota in enumerate(rotas):
                        passos = rota['legs'][0]['steps']
                        resumo = []
                        linhas_bus = []
                        
                        for passo in passos:
                            if passo['travel_mode'] == 'WALKING':
                                resumo.append("🚶")
                            elif passo['travel_mode'] == 'TRANSIT':
                                detalhes = passo['transit_details']
                                tipo = detalhes['line']['vehicle']['type']
                                nome_linha = detalhes['line']['short_name']
                                
                                if tipo == 'BUS':
                                    resumo.append(f"🚌 {nome_linha}")
                                    linhas_bus.append(nome_linha)
                                elif tipo in ['SUBWAY', 'TRAIN']:
                                    resumo.append(f"🚆 {nome_linha}")
                        
                        titulo = f"Opção {i+1}: " + " ➔ ".join(resumo)
                        opcoes_rotas[titulo] = {'rota': rota, 'linhas_bus': linhas_bus}
                    
                    if opcoes_rotas:
                        escolha = st.radio("Selecione o seu trajeto completo:", list(opcoes_rotas.keys()))
                        rota_selecionada = opcoes_rotas[escolha]['rota']
                        linhas_para_buscar = opcoes_rotas[escolha]['linhas_bus']
                    else:
                        st.warning("Nenhuma rota de transporte público encontrada.")
            except Exception as e:
                st.error(f"Erro no Google: {e}")

# --- 3. DESENHANDO O MAPA ---
with col2:
    m = folium.Map(location=[minha_lat, minha_lon], zoom_start=zoom_mapa, tiles='CartoDB positron')
    
    # Coloca o marcador verde na origem (seja do GPS ou do endereço digitado)
    if origem_final:
        folium.Marker([minha_lat, minha_lon], popup="Origem", icon=folium.Icon(color='green', icon='user', prefix='fa')).add_to(m)

    session = requests.Session()
    session.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")

    if rota_selecionada:
        passos = rota_selecionada['legs'][0]['steps']
        
        for passo in passos:
            linha_codificada = passo['polyline']['points']
            coordenadas = polyline.decode(linha_codificada)
            
            if passo['travel_mode'] == 'WALKING':
                folium.PolyLine(coordenadas, color="gray", weight=4, dash_array='10', tooltip="Caminhada").add_to(m)
            elif passo['travel_mode'] == 'TRANSIT':
                if passo['transit_details']['line']['vehicle']['type'] == 'BUS':
                    folium.PolyLine(coordenadas, color="#FF0000", weight=5, tooltip=f"Ônibus {passo['transit_details']['line']['short_name']}").add_to(m)
                else:
                    folium.PolyLine(coordenadas, color="purple", weight=5, tooltip="Metrô/Trem").add_to(m)

        onibus_encontrados = 0
        for linha_nome in linhas_para_buscar:
            numero = linha_nome.split('-')[0]
            linhas_sptrans = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={numero}").json()
            
            if linhas_sptrans:
                for l in linhas_sptrans:
                    frota = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l['cl']}").json()
                    if frota and 'vs' in frota:
                        for v in frota['vs']:
                            onibus_encontrados += 1
                            folium.Marker(
                                [v['py'], v['px']],
                                popup=f"Linha: {linha_nome} | Prefixo: {v['p']}",
                                icon=folium.Icon(color='blue', icon='bus', prefix='fa')
                            ).add_to(m)
        
        if onibus_encontrados > 0:
            st.success(f"🚌 Rota ativa! {onibus_encontrados} ônibus monitorados em tempo real.")

    else:
        st.write("Ou faça a busca manual de uma linha:")
        linha_busca = st.text_input("Digite a linha (ex: 7550):")
        if linha_busca:
            linhas = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={linha_busca}").json()
            if linhas:
                opcoes = {f"{l.get('lt')} | {l.get('tp')} ➔ {l.get('ts')}" if l.get('sl')==1 else f"{l.get('lt')} | {l.get('ts')} ➔ {l.get('tp')}": l for l in linhas}
                escolha = st.selectbox("Escolha o sentido:", list(opcoes.keys()))
                l_sel = opcoes[escolha]
                
                chave = f"{l_sel.get('lt')}-{l_sel.get('tl')}-{l_sel.get('sl')}"
                if chave in trajetos_sp:
                    folium.PolyLine(trajetos_sp[chave], color="red", weight=4).add_to(m)
                
                frota = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
                if frota and 'vs' in frota:
                    for v in frota['vs']:
                        folium.Marker([v['py'], v['px']], popup=f"Prefixo: {v['p']}", icon=folium.Icon(color='blue', icon='bus', prefix='fa')).add_to(m)
                    st.success(f"Encontrados {len(frota['vs'])} ônibus.")

    st_folium(m, width=800, height=600, returned_objects=[])
    
    if st.button('🔄 Atualizar Posições (Tempo Real)'):
        st.rerun()