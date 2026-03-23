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
import xml.etree.ElementTree as ET 

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="Hub de Mobilidade - Gilson", layout="wide")

# --- O BANHO DE LOJA (INJEÇÃO DE CSS) ---
st.markdown("""
    <style>
    /* Ocultar as marcas do Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Estilizar os botões principais */
    div.stButton > button:first-child {
        background-color: #1E1E1E;
        color: white;
        border-radius: 8px;
        border: 1px solid #333333;
        padding: 10px 24px;
        font-weight: bold;
        transition: all 0.3s ease;
        width: 100%;
    }
    div.stButton > button:first-child:hover {
        background-color: #0066cc; /* Azul vibrante ao passar o mouse */
        border-color: #0066cc;
        color: white;
        transform: translateY(-2px); /* Pequeno efeito de elevação */
    }
    </style>
""", unsafe_allow_html=True)

st.title("🌍 Hub de Mobilidade Multimodal")

# --- AS SUAS CHAVES DE ACESSO ---
TOKEN_SPTRANS = '0ff07fb8ed51fd939f51e92b03571a51fb72aad64fc19586909fd97ac1b6091a'
CHAVE_GOOGLE = 'AIzaSyAtp5jarrnwyy3_JWVfoWGbKlfEd4NjSKk' 
CHAVE_CLIMA = '1fb1b9310c7e1e3192d52f5821b0c1ab'

# --- AS CHAVES INTERNACIONAIS ---
CHAVE_TFL = 'd4fcd31a062a4b1dab6ea40cf1896241'           
CHAVE_BODS = '76765b7adeb5b7e231139229df66db24b94a12d7' # <-- Sua chave do interior da Inglaterra
CHAVE_SCOTLAND = 'CHAVE_TRAVELINE_AQUI'                  
CHAVE_RAIL = 'CHAVE_DARWIN_AQUI' 

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

aba_roteiro, aba_monitor, aba_ponto = st.tabs(["🗺️ Roteirizador Inteligente", "🚌 Monitor Clássico", "🚏 Painel do Ponto"])

# ==========================================
# ABA 1: PLANEJADOR DE ROTAS (SIMPLIFICADA)
# ==========================================
with aba_rota:
    st.subheader("🗺️ Traçar Nova Rota")
    st.write("Digite os endereços para planejar sua viagem com o Google Maps.")
    
    # --- INTERFACE LIMPA ---
    col_origem, col_destino = st.columns(2)
    with col_origem:
        origem = st.text_input("📍 Origem:", placeholder="Ex: Av. Paulista, 1500 ou 'Onde estou'")
    with col_destino:
        destino = st.text_input("🏁 Destino:", placeholder="Ex: Parque Ibirapuera")
        
    st.divider()
    
    # --- MOTOR DE BUSCA DE ROTA ---
    if st.button("Buscar Rota Rápida", type="primary", use_container_width=True):
        if origem and destino:
            with st.spinner("Calculando a melhor rota..."):
                # Fazendo a requisição para o Google Directions API
                url_directions = f"https://maps.googleapis.com/maps/api/directions/json?origin={origem}&destination={destino}&mode=transit&language=pt-BR&key={CHAVE_GOOGLE}"
                res_rota = requests.get(url_directions).json()
                
                if res_rota['status'] == 'OK':
                    rota = res_rota['routes'][0]['legs'][0]
                    
                    # Informações principais da viagem
                    tempo_total = rota['duration']['text']
                    distancia_total = rota['distance']['text']
                    
                    st.success(f"✅ Rota encontrada! Tempo estimado: **{tempo_total}** ({distancia_total})")
                    
                    st.markdown("### 📝 Passo a passo da viagem:")
                    
                    # Detalhando cada etapa da viagem
                    for passo in rota['steps']:
                        instrucao = passo['html_instructions']
                        # Removendo as tags HTML do Google para ficar um texto limpo
                        instrucao_limpa = instrucao.replace('<b>', '**').replace('</b>', '**').replace('<div style="font-size:0.9em">', ' (').replace('</div>', ')')
                        
                        modo_viagem = passo['travel_mode']
                        
                        if modo_viagem == "TRANSIT":
                            linha = passo['transit_details']['line']['short_name']
                            veiculo = passo['transit_details']['line']['vehicle']['name']
                            st.info(f"🚌 **Pegar {veiculo} (Linha {linha})**: {instrucao_limpa}")
                            st.caption(f"⏱️ Duração: {passo['duration']['text']} | 🚏 Paradas: {passo['transit_details'].get('num_stops', '?')}")
                        elif modo_viagem == "WALKING":
                            st.warning(f"🚶 **Caminhar**: {instrucao_limpa} ({passo['distance']['text']})")
                        else:
                            st.write(f"➡️ {instrucao_limpa}")
                else:
                    st.error("Não foi possível traçar uma rota entre esses dois locais. Verifique os endereços digitados.")
        else:
            st.warning("Por favor, preencha a origem e o destino antes de buscar.")
            
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
                trajeto_str = f"{l.get('ts', '')} ➔ {l.get('tp', '')}" if l.get('sl') == 1 else f"{l.get('tp', '')} ➔ {l.get('ts', '')}"
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

            try:
                hora_atual = datetime.now(pytz.timezone('America/Sao_Paulo')).hour
                tema_mapa_classico = 'CartoDB dark_matter' if (hora_atual >= 18 or hora_atual < 6) else 'CartoDB positron'
            except:
                tema_mapa_classico = 'CartoDB positron'

            m_manual = folium.Map(location=[-23.5505, -46.6333], zoom_start=12, tiles=tema_mapa_classico)

            chave_gtfs = f"{linha_sel.get('lt')}-{linha_sel.get('tl')}-{linha_sel.get('sl')}"
            if 'trajetos_sp' in locals() and chave_gtfs in trajetos_sp:
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


# ==========================================
# ABA 3: PAINEL DO PONTO (UX PREMIUM)
# ==========================================
with aba_ponto:
    st.subheader("🚏 Painel Expresso do Ponto")
    st.write("Encontre seu ponto e acompanhe as chegadas em tempo real.")
    
    col_r1, col_r2 = st.columns([8, 2])
    auto_refresh_ponto = col_r2.checkbox("🔄 Radar (30s)", value=False, key="refresh_ponto")
    
    if auto_refresh_ponto:
        st_autorefresh(interval=30000, limit=None, key="radar_paradas")

    # --- MEMÓRIA DE CURTO PRAZO (Histórico) ---
    if 'historico_pontos' not in st.session_state:
        st.session_state['historico_pontos'] = []
        
    def salvar_no_historico(nome, codigo, lat, lon):
        novo_ponto = {"nome": nome, "codigo": codigo, "lat": lat, "lon": lon}
        if novo_ponto not in st.session_state['historico_pontos']:
            st.session_state['historico_pontos'].insert(0, novo_ponto)
        # Mantém apenas os 3 últimos na memória
        st.session_state['historico_pontos'] = st.session_state['historico_pontos'][:3]

    # Variáveis globais da aba
    codigo_da_parada = None
    nome_exibicao = ""
    lat_exibicao = None
    lon_exibicao = None

    # --- A NOVA INTERFACE (ABAS INTERNAS) ---
    tab_fav, tab_linha, tab_gps, tab_nome = st.tabs([
        "⭐ Favoritos & Histórico", 
        "🚌 Por Linha", 
        "🗺️ Radar GPS", 
        "🔍 Por Nome"
    ])
    
    # 1. ABA DE FAVORITOS & HISTÓRICO
    with tab_fav:
        st.markdown("### Seus Pontos Salvos")
        pontos_vip = {
            "Parada 1 - Sabesp (Sentido Centro)": {"cp": 7203277, "lat": -23.5927, "lon": -46.6728}, 
            "Américo Brasiliense (Sentido Bairro)": {"cp": 7203285, "lat": -23.632, "lon": -46.705}
        }
        
        opcoes_dropdown = ["(Selecione um ponto abaixo)"] + [f"🌟 {nome}" for nome in pontos_vip.keys()]
        
        if st.session_state['historico_pontos']:
            opcoes_dropdown += ["--- ÚLTIMAS BUSCAS NESTA SESSÃO ---"]
            opcoes_dropdown += [f"🕒 {p['nome']}" for p in st.session_state['historico_pontos']]
            
        escolha_fav = st.selectbox("Escolha um ponto rápido:", opcoes_dropdown, key="sel_fav")
        
        if escolha_fav.startswith("🌟"):
            nome_limpo = escolha_fav.replace("🌟 ", "")
            codigo_da_parada = pontos_vip[nome_limpo]["cp"]
            nome_exibicao = nome_limpo
            lat_exibicao = pontos_vip[nome_limpo].get("lat")
            lon_exibicao = pontos_vip[nome_limpo].get("lon")
        elif escolha_fav.startswith("🕒"):
            nome_limpo = escolha_fav.replace("🕒 ", "")
            for p in st.session_state['historico_pontos']:
                if p['nome'] == nome_limpo:
                    codigo_da_parada = p['codigo']
                    nome_exibicao = p['nome']
                    lat_exibicao = p['lat']
                    lon_exibicao = p['lon']

    # 2. ABA DE RASTREIO DE LINHA
    with tab_linha:
        st.info("Acha todos os pontos do trajeto (Ida e Volta).")
        busca_linha = st.text_input("Linha (ex: 6450, 5300):", key="input_linha")
        if busca_linha:
            session = requests.Session()
            session.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
            linhas = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={busca_linha}").json()
            
            if linhas:
                opcoes_linhas = {}
                for l in linhas:
                    sentido = l.get('sl', 1)
                    if sentido == 1:
                        nome_rota = f"{l.get('c', 'Linha')} (IDA) - {l.get('tp', 'Term 1')} ➔ {l.get('ts', 'Term 2')} [ID: {l.get('cl')}]"
                    else:
                        nome_rota = f"{l.get('c', 'Linha')} (VOLTA) - {l.get('ts', 'Term 2')} ➔ {l.get('tp', 'Term 1')} [ID: {l.get('cl')}]"
                    opcoes_linhas[nome_rota] = l.get('cl')
                
                escolha_linha = st.selectbox("Selecione o sentido:", list(opcoes_linhas.keys()), key="sel_linha")
                codigo_da_linha = opcoes_linhas[escolha_linha]
                paradas_da_linha = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Parada/BuscarParadasPorLinha?codigoLinha={codigo_da_linha}").json()
                
                if paradas_da_linha:
                    st.success(f"Encontramos {len(paradas_da_linha)} paradas!")
                    opcoes_paradas = {f"{p['np']} (Endereço: {p.get('ed', 'S/N')}) - ID: {p['cp']}": p for p in paradas_da_linha}
                    escolha_parada = st.selectbox("Escolha seu ponto:", list(opcoes_paradas.keys()), key="sel_ponto_linha")
                    
                    dados_p = opcoes_paradas[escolha_parada]
                    codigo_da_parada = dados_p['cp']
                    nome_exibicao = escolha_parada.split('(')[0].strip()
                    lat_exibicao = dados_p.get('py')
                    lon_exibicao = dados_p.get('px')
                    
                    salvar_no_historico(nome_exibicao, codigo_da_parada, lat_exibicao, lon_exibicao)
                else:
                    st.warning("Trajeto indisponível para esta linha.")
            else:
                st.error("Nenhuma linha encontrada.")

    # 3. ABA RADAR GOOGLE
    with tab_gps:
        st.info("O Google acha a rua, a SPTrans acha o ponto.")
        local_atual = st.text_input("Onde você está? (Ex: 'MASP'):", key="input_gps")
        if local_atual:
            url_google = f"https://maps.googleapis.com/maps/api/geocode/json?address={local_atual}&key={CHAVE_GOOGLE}"
            res_google = requests.get(url_google).json()
            if res_google['status'] == 'OK':
                rua_oficial = ""
                for comp in res_google['results'][0]['address_components']:
                    if 'route' in comp['types']:
                        rua_oficial = comp['long_name']
                        break
                if rua_oficial:
                    st.success(f"📍 Região: **{rua_oficial}**")
                    session = requests.Session()
                    session.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
                    paradas = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Parada/Buscar?termosBusca={rua_oficial}").json()
                    if paradas:
                        opcoes_paradas = {f"{p['np']} ({p.get('ed','S/N')})": p for p in paradas}
                        escolha_parada = st.selectbox("Selecione a parada:", list(opcoes_paradas.keys()), key="sel_ponto_gps")
                        
                        dados_p = opcoes_paradas[escolha_parada]
                        codigo_da_parada = dados_p['cp']
                        nome_exibicao = escolha_parada.split('(')[0].strip()
                        lat_exibicao = dados_p.get('py')
                        lon_exibicao = dados_p.get('px')
                        salvar_no_historico(nome_exibicao, codigo_da_parada, lat_exibicao, lon_exibicao)
                    else:
                        st.warning("Nenhum ponto SPTrans nessa rua.")
                else:
                    st.warning("Rua não identificada pelo Google.")

    # 4. ABA BUSCA POR NOME
    with tab_nome:
        st.info("A busca raiz (use apenas a palavra-chave principal).")
        busca_ponto = st.text_input("Palavra-chave (ex: Bela Vista):", key="input_nome")
        if busca_ponto:
            session = requests.Session()
            session.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
            paradas = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Parada/Buscar?termosBusca={busca_ponto}").json()
            if paradas:
                opcoes_paradas = {f"{p['np']} ({p.get('ed','S/N')})": p for p in paradas}
                escolha_parada = st.selectbox("Selecione a parada:", list(opcoes_paradas.keys()), key="sel_ponto_nome")
                
                dados_p = opcoes_paradas[escolha_parada]
                codigo_da_parada = dados_p['cp']
                nome_exibicao = escolha_parada.split('(')[0].strip()
                lat_exibicao = dados_p.get('py')
                lon_exibicao = dados_p.get('px')
                salvar_no_historico(nome_exibicao, codigo_da_parada, lat_exibicao, lon_exibicao)
            else:
                st.error("Nenhum ponto encontrado.")

    # ==========================================
    # O MOTOR DO LETREIRO DIGITAL & MAPA VISUAL
    # ==========================================
    st.divider()
    
    if codigo_da_parada:
        col_info, col_mapa = st.columns([6, 4])
        
        with col_info:
            st.markdown(f"### 🚥 Chegadas em: {nome_exibicao}")
            filtro_linha = st.text_input("Filtrar linha (ex: 6500):", placeholder="Deixe em branco para ver todas", key="filtro_aba3")
            
            session = requests.Session()
            session.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
            previsao_url = f"http://api.olhovivo.sptrans.com.br/v2.1/Previsao/Parada?codigoParada={codigo_da_parada}"
            dados_previsao = session.get(previsao_url).json()
            
            if dados_previsao and 'p' in dados_previsao and 'l' in dados_previsao['p']:
                linhas_chegando = dados_previsao['p']['l']
                painel = []
                
                for linha in linhas_chegando:
                    numero_linha = linha.get('c', '')
                    if filtro_linha and filtro_linha not in numero_linha:
                        continue 
                        
                    letreiro = f"{numero_linha} - {linha.get('lt0', 'Destino')} ➔ {linha.get('lt1', 'Origem')}"
                    for veiculo in linha['vs']:
                        painel.append({"linha": letreiro, "hora_chegada": veiculo['t'], "prefixo": veiculo['p']})
                
                painel = sorted(painel, key=lambda x: x['hora_chegada'])
                
                if painel:
                    for item in painel:
                        st.info(f"🕒 **{item['hora_chegada']}** | 🚌 **{item['linha']}** (Carro: {item['prefixo']})")
                else:
                    st.warning("Nenhum ônibus correspondente ao seu filtro no momento.")
            else:
                st.warning("Não há nenhum ônibus no radar para este ponto.")
        
        with col_mapa:
            if lat_exibicao and lon_exibicao:
                st.markdown("**📍 Radar ao Vivo**")
                import pandas as pd
                
                # 1. Cria a lista de GPS começando por você (O ponto vermelho maior)
                coordenadas = [{"lat": lat_exibicao, "lon": lon_exibicao, "cor": "#FF0000", "tamanho": 100}]
                
                # 2. Caça o GPS de cada ônibus que está vindo na previsão
                if dados_previsao and 'p' in dados_previsao and 'l' in dados_previsao['p']:
                    for linha in dados_previsao['p']['l']:
                        numero_linha = linha.get('c', '')
                        
                        # Se você filtrou uma linha, só mostra os ônibus dela no mapa
                        if filtro_linha and filtro_linha not in numero_linha:
                            continue
                            
                        for veiculo in linha['vs']:
                            lat_bus = veiculo.get('py')
                            lon_bus = veiculo.get('px')
                            
                            # Se o GPS do ônibus estiver funcionando, adiciona como ponto azul
                            if lat_bus and lon_bus:
                                coordenadas.append({
                                    "lat": lat_bus, 
                                    "lon": lon_bus, 
                                    "cor": "#0000FF", # Azul
                                    "tamanho": 30     # Menorzinho
                                })
                
                # 3. Desenha o mapa final com as cores e tamanhos
                df_mapa = pd.DataFrame(coordenadas)
                try:
                    # Tenta desenhar com cores (Versões novas do Streamlit)
                    st.map(df_mapa, latitude="lat", longitude="lon", color="cor", size="tamanho", zoom=14)
                except:
                    # Plano B (Versões antigas do Streamlit aceitam só os pontos puros)
                    st.map(df_mapa, latitude="lat", longitude="lon", zoom=14)
            else:
                st.caption("Mapa indisponível (SPTrans não forneceu coordenadas para este ponto).")