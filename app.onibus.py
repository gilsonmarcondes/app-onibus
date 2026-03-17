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
    st.write("📍 **1. De onde você vai sair?**")
    localizacao = streamlit_geolocation()
    origem_digitada = st.text_input("Ou digite o endereço de partida:")
    
    st.write("🎯 **2. Para onde quer ir?**")
    destino = st.text_input("Destino:", placeholder="Ex: Avenida Paulista, 1000")

    # --- NOVO: PAINEL DE FILTROS ---
    with st.expander("⚙️ Filtros e Preferências (Moovit Style)"):
        st.write("**Escolha os meios de transporte:**")
        c1, c2, c3 = st.columns(3)
        usar_onibus = c1.checkbox("🚌 Ônibus", value=True)
        usar_metro = c2.checkbox("🚇 Metrô", value=True)
        usar_trem = c3.checkbox("🚆 Trem", value=True)

        modos_selecionados = []
        if usar_onibus: modos_selecionados.append("bus")
        if usar_metro: modos_selecionados.append("subway")
        if usar_trem: modos_selecionados.append("train")
        
        # Prevenção de erro: se o usuário desmarcar tudo, usamos todos por padrão
        if not modos_selecionados:
            modos_selecionados = ["bus", "subway", "train"]

        st.write("**Preferência de Rota:**")
        preferencia = st.radio("Priorizar:", ["⏳ Mais Rápida", "🚶 Menos Caminhada", "🔄 Menos Baldeações"], horizontal=True)

        # Traduz a escolha para o idioma do Google Maps
        routing_pref = None
        if preferencia == "🚶 Menos Caminhada":
            routing_pref = "less_walking"
        elif preferencia == "🔄 Menos Baldeações":
            routing_pref = "fewer_transfers"
    # -------------------------------
    
    origem_final = None
    minha_lat, minha_lon = -23.6331, -46.7028
    zoom_mapa = 13
    
    if origem_digitada:
        origem_final = origem_digitada
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
    detalhes_itinerario = []

    if origem_final and destino:
        with st.spinner("Analisando rotas, filtros e horários..."):
            try:
                # O Google agora recebe os nossos filtros!
                rotas = gmaps.directions(
                    origem_final, 
                    destino, 
                    mode="transit", 
                    region="br", 
                    alternatives=True,
                    transit_mode=modos_selecionados,
                    transit_routing_preference=routing_pref
                )
                
                if rotas:
                    # Força a ordenação pela rota mais rápida (menor tempo de duração em segundos)
                    rotas = sorted(rotas, key=lambda x: x['legs'][0]['duration']['value'])
                    
                    opcoes_rotas = {}
                    
                    for i, rota in enumerate(rotas):
                        passos = rota['legs'][0]['steps']
                        tempo_total = rota['legs'][0]['duration']['text'] # Pega o tempo total (Ex: 45 min)
                        
                        resumo = []
                        linhas_bus = []
                        cronograma = []
                        
                        for passo in passos:
                            if passo['travel_mode'] == 'WALKING':
                                resumo.append("🚶")
                                cronograma.append(f"🚶 Caminhada ({passo['duration']['text']})")
                            
                            elif passo['travel_mode'] == 'TRANSIT':
                                detalhes = passo['transit_details']
                                tipo = detalhes['line']['vehicle']['type']
                                nome_linha = detalhes['line']['short_name']
                                
                                hora_saida = detalhes['departure_time']['text']
                                hora_chegada = detalhes['arrival_time']['text']
                                ponto_embarque = detalhes['departure_stop']['name']
                                
                                info_passo = f"🕒 **{hora_saida}** - Embarque na linha **{nome_linha}**\n📍 *Ponto: {ponto_embarque}*\n🕒 **{hora_chegada}** - Desembarque"
                                
                                if tipo == 'BUS':
                                    resumo.append(f"🚌 {nome_linha}")
                                    linhas_bus.append(nome_linha)
                                    cronograma.append("🚌 " + info_passo)
                                elif tipo in ['SUBWAY', 'TRAIN']:
                                    resumo.append(f"🚆 {nome_linha}")
                                    cronograma.append("🚆 " + info_passo)
                        
                        # Coloca o tempo total visível no título
                        titulo = f"Opção {i+1} ({tempo_total}): " + " ➔ ".join(resumo)
                        opcoes_rotas[titulo] = {
                            'rota': rota, 
                            'linhas_bus': linhas_bus,
                            'cronograma': cronograma
                        }
                    
                    if opcoes_rotas:
                        escolha = st.radio("Selecione o seu trajeto:", list(opcoes_rotas.keys()))
                        rota_selecionada = opcoes_rotas[escolha]['rota']
                        linhas_para_buscar = opcoes_rotas[escolha]['linhas_bus']
                        detalhes_itinerario = opcoes_rotas[escolha]['cronograma']
                        
                        st.markdown("### 📋 Itinerário Detalhado")
                        for item in detalhes_itinerario:
                            st.info(item)
                            
                    else:
                        st.warning("Nenhuma rota encontrada com esses filtros.")
            except Exception as e:
                st.error(f"Erro no Google: {e}")

with col2:
    m = folium.Map(location=[minha_lat, minha_lon], zoom_start=zoom_mapa, tiles='CartoDB positron')
    
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
            st.success(f"🚌 {onibus_encontrados} ônibus monitorados em tempo real na rota.")

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