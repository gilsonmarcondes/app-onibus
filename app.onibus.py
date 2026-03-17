import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
import json
import gzip
from streamlit_geolocation import streamlit_geolocation
import googlemaps
import polyline # <-- A NOVA BIBLIOTECA QUE DESENHA AS RUAS

st.set_page_config(page_title="Monitor SPTrans - Gilson", layout="wide") # Mudei para wide para ter mais espaço

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

col1, col2 = st.columns([1, 2]) # Divide a tela para ficar mais elegante

with col1:
    st.write("📍 **1. Onde estou agora?**")
    localizacao = streamlit_geolocation()
    
    minha_lat, minha_lon = -23.6331, -46.7028
    zoom_mapa = 13
    
    if localizacao and localizacao.get('latitude'):
        minha_lat = localizacao['latitude']
        minha_lon = localizacao['longitude']
        zoom_mapa = 15
        st.success("GPS Ativo!")
    
    st.write("🎯 **2. Para onde quer ir?**")
    destino = st.text_input("Ex: Avenida Paulista, 1000")
    
    rota_selecionada = None
    linhas_para_buscar = []

    if destino and localizacao and localizacao.get('latitude'):
        with st.spinner("Analisando as melhores rotas..."):
            try:
                rotas = gmaps.directions((minha_lat, minha_lon), destino, mode="transit", region="br", alternatives=True)
                
                if rotas:
                    opcoes_rotas = {}
                    
                    # Analisa todas as rotas e monta o visual (Ex: 🚶 Andar -> 🚌 7550 -> 🚶 Andar)
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

# --- DESENHANDO O MAPA ---
with col2:
    m = folium.Map(location=[minha_lat, minha_lon], zoom_start=zoom_mapa, tiles='CartoDB positron')
    
    if localizacao and localizacao.get('latitude'):
        folium.Marker([minha_lat, minha_lon], popup="Você está aqui", icon=folium.Icon(color='green', icon='user', prefix='fa')).add_to(m)

    session = requests.Session()
    session.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")

    # SE O USUÁRIO ESCOLHEU UMA ROTA DO GOOGLE:
    if rota_selecionada:
        passos = rota_selecionada['legs'][0]['steps']
        
        # 1. Desenha cada passo do trajeto
        for passo in passos:
            # O Google manda o desenho perfeito da rua criptografado. A polyline descriptografa!
            linha_codificada = passo['polyline']['points']
            coordenadas = polyline.decode(linha_codificada)
            
            if passo['travel_mode'] == 'WALKING':
                # Linha cinza tracejada para caminhada
                folium.PolyLine(coordenadas, color="gray", weight=4, dash_array='10', tooltip="Caminhada").add_to(m)
            elif passo['travel_mode'] == 'TRANSIT':
                if passo['transit_details']['line']['vehicle']['type'] == 'BUS':
                    # Linha vermelha para ônibus
                    folium.PolyLine(coordenadas, color="#FF0000", weight=5, tooltip=f"Ônibus {passo['transit_details']['line']['short_name']}").add_to(m)
                else:
                    # Linha roxa para Metrô/Trem
                    folium.PolyLine(coordenadas, color="purple", weight=5, tooltip="Metrô/Trem").add_to(m)

        # 2. Busca os ônibus na SPTrans para TODAS as linhas da rota
        onibus_encontrados = 0
        for linha_nome in linhas_para_buscar:
            numero = linha_nome.split('-')[0]
            linhas_sptrans = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={numero}").json()
            
            if linhas_sptrans:
                # Busca nas duas direções da linha para garantir que você veja os ônibus chegando
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
            st.success(f"🚌 Rota ativa! {onibus_encontrados} ônibus dessas linhas monitorados em tempo real.")

    # SE NÃO TEM ROTA, USA A BUSCA MANUAL CLÁSSICA:
    else:
        st.write("Ou faça a busca manual de uma linha:")
        linha_busca = st.text_input("Digite a linha (ex: 7550):")
        if linha_busca:
            linhas = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={linha_busca}").json()
            if linhas:
                opcoes = {f"{l.get('lt')} | {l.get('tp')} ➔ {l.get('ts')}" if l.get('sl')==1 else f"{l.get('lt')} | {l.get('ts')} ➔ {l.get('tp')}": l for l in linhas}
                escolha = st.selectbox("Escolha o sentido:", list(opcoes.keys()))
                l_sel = opcoes[escolha]
                
                # Desenha rua do GTFS
                chave = f"{l_sel.get('lt')}-{l_sel.get('tl')}-{l_sel.get('sl')}"
                if chave in trajetos_sp:
                    folium.PolyLine(trajetos_sp[chave], color="red", weight=4).add_to(m)
                
                # Pega frota
                frota = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
                if frota and 'vs' in frota:
                    for v in frota['vs']:
                        folium.Marker([v['py'], v['px']], popup=f"Prefixo: {v['p']}", icon=folium.Icon(color='blue', icon='bus', prefix='fa')).add_to(m)
                    st.success(f"Encontrados {len(frota['vs'])} ônibus.")

    st_folium(m, width=800, height=600, returned_objects=[])
    
    if st.button('🔄 Atualizar Posições (Tempo Real)'):
        st.rerun()