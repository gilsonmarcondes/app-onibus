import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
import json
import gzip
from streamlit_geolocation import streamlit_geolocation
import googlemaps
import polyline
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Monitor SPTrans - Gilson", layout="wide")

st.title("🗺️ Roteirizador Multimodal SPTrans")

# --- CHAVES DE ACESSO ---
TOKEN_SPTRANS = '0ff07fb8ed51fd939f51e92b03571a51fb72aad64fc19586909fd97ac1b6091a'
CHAVE_GOOGLE = 'AIzaSyAtp5jarrnwyy3_JWVfoWGbKlfEd4NjSKk' 
CHAVE_CLIMA = '1fb1b9310c7e1e3192d52f5821b0c1ab' # <-- SUA NOVA CHAVE AQUI

gmaps = googlemaps.Client(key=CHAVE_GOOGLE)

# --- FUNÇÃO DO CLIMA ---
def obter_clima_destino(lat, lon, api_key):
    # Consulta a API do OpenWeatherMap em português e em Celsius (metric)
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=pt_br"
    try:
        resposta = requests.get(url).json()
        if resposta.get('main'):
            temp = round(resposta['main']['temp'])
            descricao = resposta['weather'][0]['description'].capitalize()
            # Mapeia ícones simples baseado na descrição
            icone = "☀️" if "limpo" in descricao.lower() else "☁️" if "nublado" in descricao.lower() else "🌧️" if "chuva" in descricao.lower() else "⛅"
            return f"{icone} **{temp}°C** - {descricao}"
    except:
        pass
    return None

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

    st.write("🕒 **3. Quando você quer viajar?**")
    opcao_horario = st.selectbox("Escolha o momento:", ["Sair agora", "Partir às...", "Chegar até..."])
    
    if opcao_horario == "Sair agora":
        st_autorefresh(interval=30000, limit=None, key="radar_onibus")
        st.caption("⏳ *Radar Automático Ativado (Atualiza a cada 30s)*")
    
    data_viagem = None
    hora_viagem = None
    
    if opcao_horario != "Sair agora":
        cd, ch = st.columns(2)
        data_viagem = cd.date_input("Data da viagem")
        hora_viagem = ch.time_input("Hora da viagem")
    st.divider()

    with st.expander("⚙️ Filtros e Preferências"):
        st.write("**Escolha os meios de transporte:**")
        c1, c2, c3 = st.columns(3)
        usar_onibus = c1.checkbox("🚌 Ônibus", value=True)
        usar_metro = c2.checkbox("🚇 Metrô", value=True)
        usar_trem = c3.checkbox("🚆 Trem", value=True)

        modos_selecionados = []
        if usar_onibus: modos_selecionados.append("bus")
        if usar_metro: modos_selecionados.append("subway")
        if usar_trem: modos_selecionados.append("train")
        
        if not modos_selecionados:
            modos_selecionados = ["bus", "subway", "train"]

        preferencia = st.radio("Priorizar:", ["⏳ Mais Rápida", "🚶 Menos Caminhada", "🔄 Menos Baldeações"], horizontal=True)

        routing_pref = None
        if preferencia == "🚶 Menos Caminhada": routing_pref = "less_walking"
        elif preferencia == "🔄 Menos Baldeações": routing_pref = "fewer_transfers"
    
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
    destino_lat = None
    destino_lon = None

    if origem_final and destino:
        with st.spinner("Calculando rotas e verificando o clima..."):
            try:
                fuso_sp = pytz.timezone('America/Sao_Paulo')
                
                instrucoes_google = {
                    "mode": "transit",
                    "region": "br",
                    "alternatives": True,
                    "transit_mode": modos_selecionados,
                    "transit_routing_preference": routing_pref
                }

                if opcao_horario == "Sair agora":
                    instrucoes_google["departure_time"] = datetime.now(fuso_sp)
                else:
                    dt_escolhida = fuso_sp.localize(datetime.combine(data_viagem, hora_viagem))
                    if opcao_horario == "Partir às...":
                        instrucoes_google["departure_time"] = dt_escolhida
                    elif opcao_horario == "Chegar até...":
                        instrucoes_google["arrival_time"] = dt_escolhida

                rotas = gmaps.directions(origem_final, destino, **instrucoes_google)
                
                if rotas:
                    rotas = sorted(rotas, key=lambda x: x['legs'][0]['duration']['value'])
                    opcoes_rotas = {}
                    
                    # Captura as coordenadas finais do destino para ver o clima lá
                    destino_lat = rotas[0]['legs'][0]['end_location']['lat']
                    destino_lon = rotas[0]['legs'][0]['end_location']['lng']
                    
                    for i, rota in enumerate(rotas):
                        passos = rota['legs'][0]['steps']
                        tempo_total = rota['legs'][0]['duration']['text']
                        
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
                        
                        # --- EXIBE O CLIMA ANTES DO ITINERÁRIO ---
                        if CHAVE_CLIMA != 'COLOQUE_A_SUA_CHAVE_DO_CLIMA_AQUI':
                            clima_atual = obter_clima_destino(destino_lat, destino_lon, CHAVE_CLIMA)
                            if clima_atual:
                                st.success(f"Condições no destino agora: {clima_atual}")
                        
                        st.markdown("### 📋 Itinerário Detalhado")
                        for item in detalhes_itinerario:
                            st.info(item)
                            
                    else:
                        st.warning("Nenhuma rota encontrada para este horário.")
            except Exception as e:
                st.error(f"Erro na busca: {e}")

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

        if opcao_horario == "Sair agora":
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
                st.warning("Nenhum ônibus desta linha localizado no radar agora.")

    st_folium(m, width=800, height=600, returned_objects=[])
    
    if st.button('🔄 Forçar Atualização Imediata'):
        st.rerun()