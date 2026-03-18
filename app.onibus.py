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
import xml.etree.ElementTree as ET # <-- Nova biblioteca para ler os dados dos trens britânicos

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="Hub de Mobilidade - Gilson", layout="wide")

st.title("🌍 Hub de Mobilidade Multimodal")

# --- AS SUAS CHAVES DE ACESSO ---
TOKEN_SPTRANS = '0ff07fb8ed51fd939f51e92b03571a51fb72aad64fc19586909fd97ac1b6091a'
CHAVE_GOOGLE = 'AIzaSyAtp5jarrnwyy3_JWVfoWGbKlfEd4NjSKk' 
CHAVE_CLIMA = '1fb1b9310c7e1e3192d52f5821b0c1ab'

# --- AS CHAVES INTERNACIONAIS ---
CHAVE_TFL = 'd4fcd31a062a4b1dab6ea40cf1896241'           
CHAVE_BODS = '76765b7adeb5b7e231139229df66db24b94a12d7'                           
CHAVE_SCOTLAND = 'CHAVE_TRAVELINE_AQUI'                  
CHAVE_RAIL = 'CHAVE_DARWIN_AQUI' # <-- Cole a sua chave da National Rail aqui

gmaps = googlemaps.Client(key=CHAVE_GOOGLE)

def obter_clima_destino(lat, lon, api_key):
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=pt_br"
    try:
        resposta = requests.get(url).json()
        if resposta.get('main'):
            temp = round(resposta['main']['temp'])
            descricao = resposta['weather'][0]['description'].capitalize()
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

# --- INICIALIZAR A MEMÓRIA DO APLICATIVO ---
if 'memoria_origem' not in st.session_state:
    st.session_state.memoria_origem = ""
if 'memoria_destino' not in st.session_state:
    st.session_state.memoria_destino = ""

aba_roteiro, aba_monitor = st.tabs(["🗺️ Roteirizador Inteligente", "🚌 Monitor Clássico (SPTrans)"])

# ==========================================
# ABA 1: O ROTEIRIZADOR GLOBAL
# ==========================================
with aba_roteiro:
    col1, col2 = st.columns([1, 2])

    with col1:
        st.write("🌍 **1. Qual sistema de radar vamos usar?**")
        regiao_selecionada = st.selectbox(
            "Escolha a região para ligar o radar em tempo real:", 
            ["🇧🇷 São Paulo (SPTrans)", "🇬🇧 Londres (TfL Unified API)", "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Inglaterra Interior (BODS)", "🏴󠁧󠁢󠁳󠁣󠁴󠁿 Escócia (Traveline)", "🚆 Reino Unido (National Rail)"]
        )
        st.divider()

        # --- OS BOTÕES DE ACESSO RÁPIDO ---
        st.write("🌟 **Rotas Favoritas (Acesso Rápido)**")
        col_btn1, col_btn2 = st.columns(2)
        
        if col_btn1.button("🎓 Ir para UNESP"):
            st.session_state.memoria_origem = "SEU ENDERECO DE CASA AQUI, Sao Paulo"
            st.session_state.memoria_destino = "UNESP, Sao Paulo"
            st.rerun()

        if col_btn2.button("🏠 Voltar para Casa"):
            st.session_state.memoria_origem = "UNESP, Sao Paulo"
            st.session_state.memoria_destino = "SEU ENDERECO DE CASA AQUI, Sao Paulo"
            st.rerun()
        st.divider()

        st.write("📍 **2. De onde você vai sair?**")
        localizacao = streamlit_geolocation()
        origem_digitada = st.text_input("Ou digite o endereço de partida:", key="memoria_origem", placeholder="Ex: London Eye, Ibis Kensington...")
        
        st.write("🎯 **3. Para onde quer ir?**")
        destino = st.text_input("Destino:", key="memoria_destino", placeholder="Ex: Big Ben, Inverness...")

        st.write("🕒 **4. Quando você quer viajar?**")
        opcao_horario = st.selectbox("Escolha o momento:", ["Sair agora", "Partir às...", "Chegar até..."])
        
        if opcao_horario == "Sair agora":
            st_autorefresh(interval=30000, limit=None, key="radar_roteiro")
            st.caption("⏳ *Radar Automático Ativado (Atualiza a cada 30s)*")
        
        data_viagem = None
        hora_viagem = None
        
        if opcao_horario != "Sair agora":
            cd, ch = st.columns(2)
            data_viagem = cd.date_input("Data da viagem")
            hora_viagem = ch.time_input("Hora da viagem")
        st.divider()

        with st.expander("⚙️ Filtros e Preferências"):
            c1_f, c2_f, c3_f = st.columns(3)
            usar_onibus = c1_f.checkbox("🚌 Ônibus", value=True)
            usar_metro = c2_f.checkbox("🚇 Metrô/Tube", value=True)
            usar_trem = c3_f.checkbox("🚆 Trem", value=True)

            modos_selecionados = []
            if usar_onibus: modos_selecionados.append("bus")
            if usar_metro: modos_selecionados.append("subway")
            if usar_trem: modos_selecionados.append("train")
            if not modos_selecionados: modos_selecionados = ["bus", "subway", "train"]

            preferencia = st.radio("Priorizar:", ["⏳ Mais Rápida", "🚶 Menos Caminhada", "🔄 Menos Baldeações"], horizontal=True)
            routing_pref = "less_walking" if preferencia == "🚶 Menos Caminhada" else "fewer_transfers" if preferencia == "🔄 Menos Baldeações" else None
        
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
            except: pass
        elif localizacao and localizacao.get('latitude'):
            minha_lat = localizacao['latitude']
            minha_lon = localizacao['longitude']
            origem_final = (minha_lat, minha_lon)
            zoom_mapa = 15
        
        rota_selecionada = None
        linhas_para_buscar = []

        if origem_final and destino:
            with st.spinner("A calcular rotas e fuso horário..."):
                try:
                    if "São Paulo" in regiao_selecionada:
                        fuso = pytz.timezone('America/Sao_Paulo')
                        regiao_google = "br"
                    else:
                        fuso = pytz.timezone('Europe/London')
                        regiao_google = "uk"
                    
                    instrucoes_google = {
                        "mode": "transit", "region": regiao_google,
                        "alternatives": True, "transit_mode": modos_selecionados, "transit_routing_preference": routing_pref
                    }

                    if opcao_horario == "Sair agora": instrucoes_google["departure_time"] = datetime.now(fuso)
                    else:
                        dt_escolhida = fuso.localize(datetime.combine(data_viagem, hora_viagem))
                        if opcao_horario == "Partir às...": instrucoes_google["departure_time"] = dt_escolhida
                        elif opcao_horario == "Chegar até...": instrucoes_google["arrival_time"] = dt_escolhida

                    rotas = gmaps.directions(origem_final, destino, **instrucoes_google)
                    
                    if rotas:
                        rotas = sorted(rotas, key=lambda x: x['legs'][0]['duration']['value'])
                        opcoes_rotas = {}
                        
                        destino_lat = rotas[0]['legs'][0]['end_location']['lat']
                        destino_lon = rotas[0]['legs'][0]['end_location']['lng']
                        
                        for i, rota in enumerate(rotas):
                            passos = rota['legs'][0]['steps']
                            tempo_total = rota['legs'][0]['duration']['text']
                            resumo, linhas_bus, cronograma = [], [], []
                            
                            for passo in passos:
                                if passo['travel_mode'] == 'WALKING':
                                    resumo.append("🚶")
                                    cronograma.append(f"🚶 Caminhada ({passo['duration']['text']})")
                                elif passo['travel_mode'] == 'TRANSIT':
                                    detalhes = passo['transit_details']
                                    tipo = detalhes['line']['vehicle']['type']
                                    nome_linha = detalhes['line'].get('short_name') or detalhes['line'].get('name') or "Linha"
                                    
                                    hora_saida = detalhes['departure_time']['text']
                                    hora_chegada = detalhes['arrival_time']['text']
                                    ponto_embarque = detalhes['departure_stop']['name']
                                    info_passo = f"🕒 **{hora_saida}** - Embarque: **{nome_linha}**\n📍 *Ponto: {ponto_embarque}*\n🕒 **{hora_chegada}** - Desembarque"
                                    
                                    if tipo == 'BUS':
                                        resumo.append(f"🚌 {nome_linha}")
                                        linhas_bus.append(nome_linha)
                                        cronograma.append("🚌 " + info_passo)
                                    elif tipo in ['SUBWAY', 'TRAIN']:
                                        resumo.append(f"🚆 {nome_linha}")
                                        linhas_bus.append(nome_linha)
                                        cronograma.append("🚆 " + info_passo)
                            
                            titulo = f"Opção {i+1} ({tempo_total}): " + " ➔ ".join(resumo)
                            opcoes_rotas[titulo] = {'rota': rota, 'linhas_bus': linhas_bus, 'cronograma': cronograma}
                        
                        if opcoes_rotas:
                            escolha = st.radio("Selecione o seu trajeto:", list(opcoes_rotas.keys()))
                            rota_selecionada = opcoes_rotas[escolha]['rota']
                            linhas_para_buscar = opcoes_rotas[escolha]['linhas_bus']
                            
                            if CHAVE_CLIMA != 'COLOQUE_A_SUA_CHAVE_DO_CLIMA_AQUI':
                                clima_atual = obter_clima_destino(destino_lat, destino_lon, CHAVE_CLIMA)
                                if clima_atual: st.success(f"Condições no destino: {clima_atual}")
                            
                            st.markdown("### 📋 Itinerário Detalhado")
                            for item in opcoes_rotas[escolha]['cronograma']: st.info(item)
                        else:
                            st.warning("Nenhuma rota encontrada.")
                except Exception as e:
                    st.error(f"Erro na busca: {e}")

    with col2:
        # --- MODO ESCURO DINÂMICO ---
        try:
            # Pega a hora baseado na região (SP ou Londres)
            if "São Paulo" in regiao_selecionada:
                fuso_mapa = pytz.timezone('America/Sao_Paulo')
            else:
                fuso_mapa = pytz.timezone('Europe/London')
                
            hora_atual = datetime.now(fuso_mapa).hour
            if hora_atual >= 18 or hora_atual < 6:
                tema_mapa = 'CartoDB dark_matter'
            else:
                tema_mapa = 'CartoDB positron'
        except:
            tema_mapa = 'CartoDB positron'

        m_roteiro = folium.Map(location=[minha_lat, minha_lon], zoom_start=zoom_mapa, tiles=tema_mapa)
        
        if origem_final: folium.Marker([minha_lat, minha_lon], popup="Origem", icon=folium.Icon(color='green', icon='user', prefix='fa')).add_to(m_roteiro)

        if rota_selecionada:
            for passo in rota_selecionada['legs'][0]['steps']:
                coordenadas = polyline.decode(passo['polyline']['points'])
                if passo['travel_mode'] == 'WALKING':
                    folium.PolyLine(coordenadas, color="gray", weight=4, dash_array='10').add_to(m_roteiro)
                elif passo['travel_mode'] == 'TRANSIT':
                    nome_tooltip = passo['transit_details']['line'].get('short_name') or passo['transit_details']['line'].get('name') or "Linha"
                    if passo['transit_details']['line']['vehicle']['type'] == 'BUS':
                        folium.PolyLine(coordenadas, color="#FF0000", weight=5, tooltip=f"Ônibus {nome_tooltip}").add_to(m_roteiro)
                    else:
                        folium.PolyLine(coordenadas, color="purple", weight=5, tooltip=f"Trilhos {nome_tooltip}").add_to(m_roteiro)

            st_folium(m_roteiro, width=800, height=500, returned_objects=[], key="mapa_roteiro")

            if opcao_horario == "Sair agora":
                if "São Paulo" in regiao_selecionada:
                    session = requests.Session()
                    session.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
                    onibus_encontrados = 0
                    for linha_nome in linhas_para_buscar:
                        numero = linha_nome.split('-')[0]
                        linhas_sptrans = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={numero}").json()
                        if isinstance(linhas_sptrans, list):
                            for l in linhas_sptrans:
                                frota = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l['cl']}").json()
                                if frota and 'vs' in frota:
                                    for v in frota['vs']:
                                        onibus_encontrados += 1
                                        folium.Marker([v['py'], v['px']], popup=f"SPTrans | Prefixo: {v['p']}", icon=folium.Icon(color='blue', icon='bus', prefix='fa')).add_to(m_roteiro) 
                    if onibus_encontrados > 0: 
                        st.success(f"🚌 {onibus_encontrados} ônibus rastreados na SPTrans. Atualize a página para ver no mapa.")

                elif "Londres" in regiao_selecionada:
                    if CHAVE_TFL == 'COLOQUE_A_SUA_CHAVE_LONDRES_AQUI':
                        st.warning("⚠️ Insira a chave da TfL no código para ver os painéis de chegada ao vivo.")
                    else:
                        st.info("📡 A ligar aos servidores da Transport for London...")
                        veiculos_encontrados = 0
                        veiculos_vistos = set()
                        st.markdown("### 🇬🇧 Painel de Chegadas ao Vivo (TfL)")
                        for linha_nome in linhas_para_buscar:
                            linha_id = linha_nome.lower().replace(" line", "").replace(" ", "")
                            try:
                                url_tfl = f"https://api.tfl.gov.uk/Line/{linha_id}/Arrivals?app_key={CHAVE_TFL}"
                                resposta_tfl = requests.get(url_tfl).json()
                                if isinstance(resposta_tfl, list):
                                    for previsao in resposta_tfl:
                                        id_veiculo = previsao.get('vehicleId')
                                        if id_veiculo and str(id_veiculo) != "00000" and id_veiculo not in veiculos_vistos:
                                            veiculos_vistos.add(id_veiculo)
                                            veiculos_encontrados += 1
                                            estacao = previsao.get('stationName', 'Paragem')
                                            minutos = previsao.get('timeToStation', 0) // 60
                                            tempo_texto = "🚨 **A Chegar!**" if minutos == 0 else f"**{minutos} min**"
                                            st.write(f"🚇 **Linha {linha_nome}**: Chega a *{estacao}* em {tempo_texto}")
                            except Exception as e:
                                pass
                        if veiculos_encontrados == 0:
                            st.warning("A TfL não reportou veículos próximos para esta rota neste exato momento.")

                elif "BODS" in regiao_selecionada:
                    st.warning("⚠️ Insira a chave do BODS para rastrear os autocarros intermunicipais.")
                elif "Escócia" in regiao_selecionada:
                    st.warning("⚠️ Insira a chave da Traveline para ativar o radar escocês.")
                
                # 5. COMBOIOS (NATIONAL RAIL) - O Painel das Estações (SOAP XML)
                elif "National Rail" in regiao_selecionada:
                    if CHAVE_RAIL == 'CHAVE_DARWIN_AQUI':
                        st.warning("⚠️ Insira a chave da Darwin API (Token) no código para ativar o radar ferroviário.")
                    else:
                        st.info("📡 A ligar ao painel central da National Rail...")
                        
                        # Dicionário de Códigos de Estação (CRS) 
                        dicionario_crs = {
                            "kings cross": "KGX", "edinburgh": "EDB", "inverness": "INV",
                            "euston": "EUS", "victoria": "VIC", "waterloo": "WAT", 
                            "paddington": "PAD", "st pancras": "STP"
                        }
                        
                        origem_limpa = origem_digitada.lower().replace("'", "").replace("london ", "")
                        codigo_estacao = None
                        
                        for nome_estacao, crs in dicionario_crs.items():
                            if nome_estacao in origem_limpa:
                                codigo_estacao = crs
                                break
                                
                        if codigo_estacao:
                            st.markdown(f"### 🚆 Painel de Partidas: {codigo_estacao.upper()}")
                            
                            xml_request = f"""<?xml version="1.0"?>
                            <SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns1="http://thalesgroup.com/RTTI/2017-10-01/ldb/" xmlns:ns2="http://thalesgroup.com/RTTI/2013-11-28/Token/types">
                              <SOAP-ENV:Header>
                                <ns2:AccessToken>
                                  <ns2:TokenValue>{CHAVE_RAIL}</ns2:TokenValue>
                                </ns2:AccessToken>
                              </SOAP-ENV:Header>
                              <SOAP-ENV:Body>
                                <ns1:GetDepartureBoardRequest>
                                  <ns1:numRows>5</ns1:numRows>
                                  <ns1:crs>{codigo_estacao}</ns1:crs>
                                </ns1:GetDepartureBoardRequest>
                              </SOAP-ENV:Body>
                            </SOAP-ENV:Envelope>"""
                            
                            headers = {'Content-Type': 'text/xml'}
                            url_darwin = "https://lite.realtime.nationalrail.co.uk/OpenLDBWS/ldb11.asmx"
                            
                            try:
                                resposta_rail = requests.post(url_darwin, data=xml_request, headers=headers)
                                
                                if resposta_rail.status_code == 200:
                                    root = ET.fromstring(resposta_rail.content)
                                    namespaces = {'lt7': 'http://thalesgroup.com/RTTI/2017-10-01/ldb/types'}
                                    servicos = root.findall('.//lt7:trainServices/lt7:service', namespaces)
                                    
                                    if servicos:
                                        for trem in servicos:
                                            destino_trem = trem.find('lt7:destination/lt7:location/lt7:locationName', namespaces).text
                                            hora_oficial = trem.find('lt7:std', namespaces).text
                                            hora_estimada = trem.find('lt7:etd', namespaces).text
                                            plataforma = trem.find('lt7:platform', namespaces)
                                            plat_texto = plataforma.text if plataforma is not None else "Aguarde..."
                                            
                                            status = "✅ No Horário" if hora_estimada == "On time" else f"⚠️ Atrasado para {hora_estimada}"
                                            
                                            st.info(f"🕒 **{hora_oficial}** ➔ **{destino_trem}** | Plataforma: **{plat_texto}** | {status}")
                                    else:
                                        st.warning("Nenhum trem programado para as próximas horas nesta estação.")
                            except Exception as e:
                                st.error(f"Erro ao ler os dados da National Rail: {e}")
                        else:
                            st.warning("Para ver o painel ao vivo, digite uma estação principal na origem (ex: King's Cross, Edinburgh, Inverness, Paddington).")

# ==========================================
# ABA 2: O MONITOR CLÁSSICO (BUSCA DIRETA)
# ==========================================
with aba_monitor:
    st.subheader("🚌 Monitor de Frota SPTrans")
    
    col_refresh = st.columns([8, 2])[1]
    auto_refresh = col_refresh.checkbox("🔄 Radar Automático (30s)", value=False)
    if auto_refresh:
        st_autorefresh(interval=30000, limit=None, key="radar_classico")

    linha_busca_manual = st.text_input("Digite o número da linha (ex: 6500):", placeholder="6500")
    
    if linha_busca_manual:
        session = requests.Session()
        session.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        
        linhas = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={linha_busca_manual}").json()
        
        if linhas:
            st.write("Escolha o sentido desejado:")
            opcoes_linha = {}
            dados_linhas_manual = {}
            
            for l in linhas:
                trajeto_str = f"{l.get('tp', '')} ➔ {l.get('ts', '')}" if l.get('sl') == 1 else f"{l.get('ts', '')} ➔ {l.get('tp', '')}"
                nome_formatado = f"{l.get('lt', '')} - {l.get('tl', '')} ({trajeto_str})"
                opcoes_linha[nome_formatado] = l['cl']
                dados_linhas_manual[nome_formatado] = l
            
            escolha_manual = st.selectbox("", list(opcoes_linha.keys()), label_visibility="collapsed")
            id_linha_manual = opcoes_linha[escolha_manual]
            linha_sel = dados_linhas_manual[escolha_manual]

            st.markdown(f"### Localização Real - {escolha_manual}")

            frota_manual = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={id_linha_manual}").json()
            qtd_onibus = len(frota_manual['vs']) if (frota_manual and 'vs' in frota_manual) else 0
            
            if qtd_onibus > 0:
                st.success(f"Encontrados {qtd_onibus} ônibus em circulação.")
            else:
                st.warning("Nenhum ônibus desta linha operando neste sentido agora.")

            # Modo Escuro no Monitor Clássico também
            try:
                hora_atual = datetime.now(pytz.timezone('America/Sao_Paulo')).hour
                tema_mapa_classico = 'CartoDB dark_matter' if (hora_atual >= 18 or hora_atual < 6) else 'CartoDB positron'
            except:
                tema_mapa_classico = 'CartoDB positron'

            m_manual = folium.Map(location=[-23.5505, -46.6333], zoom_start=12, tiles=tema_mapa_classico)

            chave_gtfs = f"{linha_sel.get('lt')}-{linha_sel.get('tl')}-{linha_sel.get('sl')}"
            if chave_gtfs in trajetos_sp:
                folium.PolyLine(trajetos_sp[chave_gtfs], color="#FF0000", weight=4, opacity=0.7).add_to(m_manual)

            if qtd_onibus > 0:
                for v in frota_manual['vs']:
                    folium.Marker(
                        [v['py'], v['px']], 
                        popup=f"Prefixo: {v['p']}", 
                        icon=folium.Icon(color='blue', icon='bus', prefix='fa')
                    ).add_to(m_manual)
            
            st_folium(m_manual, width=1000, height=600, returned_objects=[], key="mapa_manual")
            
            if not auto_refresh:
                if st.button('🔄 Atualizar Manualmente'):
                    st.rerun()
        else:
            st.error("Linha não encontrada na base da SPTrans.")