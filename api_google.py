import requests
import streamlit as st

@st.cache_data(ttl=3600, show_spinner=False)
def buscar_lugares_google(query, chave_google):
    """Busca endereços no Google com cache de 1 hora (3600 segundos)"""
    if not query or len(query) < 3: 
        return {}
        
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    
    # A MÁGICA ACONTECE AQUI: Deixamos o 'requests' formatar a URL
    parametros = {
        "query": query,
        "key": chave_google,
        "language": "pt-BR"
    }
    
    try:
        res = requests.get(url, params=parametros, timeout=10).json()
        
        if res.get('status') == 'OK':
            return {item['formatted_address']: item['geometry']['location'] for item in res['results']}
        elif res.get('status') == 'ZERO_RESULTS':
            return {}
        else:
            st.warning(f"Atenção (Google): {res.get('status')} - Verifique se a Places API está ativada no console.")
            
    except Exception as e:
        st.error(f"Erro na busca de endereço: {e}")
        
    return {}