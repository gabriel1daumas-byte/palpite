import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, time, timedelta
import pytz
import base64

# --- CONFIGURAÇÃO INICIAL E CONEXÃO ---
st.set_page_config(page_title="Bolão da Galera", page_icon="🏆", layout="wide")

# LISTA OFICIAL DE TIMES DA SÉRIE A - 2026
TIMES_SERIE_A = sorted([
    "Athletico-PR", "Atlético-MG", "Bahia", "Botafogo", "Bragantino",
    "Chapecoense", "Corinthians", "Coritiba", "Cruzeiro", "Flamengo",
    "Fluminense", "Grêmio", "Internacional", "Mirassol", "Palmeiras",
    "Remo", "Santos", "São Paulo", "Vasco", "Vitória"
])

# Truque de CSS para forçar o Combo sem scroll
st.markdown("""
    <style>
    div[data-baseweb="popover"] ul {
        max-height: 800px !important;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()
fuso_br = pytz.timezone('America/Sao_Paulo')

# --- FUNÇÕES DE SUPORTE E PAGINAÇÃO ---
def buscar_todos_palpites(filtro_ids_jogos=None):
    dados = []
    inicio = 0
    while True:
        query = supabase.table("palpites").select("*")
        if filtro_ids_jogos is not None:
            if len(filtro_ids_jogos) == 0:
                return []
            query = query.in_("id_jogo", filtro_ids_jogos)
            
        res = query.range(inicio, inicio + 999).execute()
        dados.extend(res.data)
        
        if len(res.data) < 1000:
            break
        inicio += 1000
    return dados

def buscar_todos_jogos_encerrados():
    dados = []
    inicio = 0
    while True:
        res = supabase.table("jogos").select("*").not_.is_("resultado_real", "null").range(inicio, inicio + 999).execute()
        dados.extend(res.data)
        if len(res.data) < 1000:
            break
        inicio += 1000
    return dados

def converter_para_br(data_string):
    if data_string.endswith('Z'):
        data_string = data_string[:-1] + '+00:00'
    return datetime.fromisoformat(data_string).astimezone(fuso_br)

def get_rodada_ativa():
    try:
        res = supabase.table("configuracoes").select("rodada_ativa").eq("id", 1).execute()
        if res.data:
            return res.data[0]['rodada_ativa']
    except:
        pass
    return 1

def codificar_sessao(email):
    return base64.b64encode(email.encode()).decode()

def decodificar_sessao(codigo):
    try:
        return base64.b64decode(codigo.encode()).decode()
    except:
        return None

# FÓRMULA MÁGICA PARA ORDENAR JOGOS POR HORÁRIO EXATO
def ordenar_jogos_por_horario(lista_jogos):
    def get_ts(j):
        hf = j.get('horario_fechamento')
        if not hf:
            return float('inf')
        try:
            return converter_para_br(hf).timestamp()
        except Exception:
            return float('inf')
    return sorted(lista_jogos, key=get_ts)

if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.nome_usuario = ""
    st.session_state.email_usuario = ""
    st.session_state.is_admin = False

if "sessao" in st.query_params and not st.session_state.logado:
    email_decodificado = decodificar_sessao(st.query_params["sessao"])
    if email_decodificado:
        res = supabase.table("usuarios").select("*").eq("email", email_decodificado).execute()
        if res.data:
            usuario = res.data[0]
            st.session_state.logado = True
            st.session_state.nome_usuario = usuario['nome']
            st.session_state.email_usuario = usuario['email']
            st.session_state.is_admin = usuario.get('is_admin', False)

# ==========================================
# ECRÃ DE ACESSO
# ==========================================
if not st.session_state.logado:
    st.title("🔒 Acesso ao Bolão")
    st.write("Identifique-se para aceder aos palpites.")
    
    with st.form("form_login_unificado"):
        email_digitado = st.text_input("E-mail", autocomplete="username")
        senha_digitada = st.text_input("Palavra-passe", type="password", autocomplete="current-password")
        submit = st.form_submit_button("Entrar", use_container_width=True)
        
        if submit:
            if email_digitado and senha_digitada:
                email_limpo = email_digitado.lower().strip()
                resposta = supabase.table("usuarios").select("*").eq("email", email_limpo).execute()
                
                if len(resposta.data) > 0:
                    usuario = resposta.data[0]
                    
                    if not usuario.get("senha"):
                        supabase.table("usuarios").update({"senha": senha_digitada}).eq("email", email_limpo).execute()
                        st.success("Primeiro acesso detetado! Palavra-passe registada.")
                        st.query_params["sessao"] = codificar_sessao(email_limpo)
                        st.session_state.logado = True
                        st.session_state.nome_usuario = usuario['nome']
                        st.session_state.email_usuario = email_limpo
                        st.session_state.is_admin = usuario.get('is_admin', False)
                        st.rerun()
                    else:
                        if senha_digitada == usuario["senha"]:
                            st.query_params["sessao"] = codificar_sessao(email_limpo)
                            st.session_state.logado = True
                            st.session_state.nome_usuario = usuario['nome']
                            st.session_state.email_usuario = email_limpo
                            st.session_state.is_admin = usuario.get('is_admin', False)
                            st.rerun()
                        else:
                            st.error("Palavra-passe incorreta!")
                else:
                    st.error("E-mail não encontrado! Fale com o administrador.")
            else:
                st.warning("Por favor, preencha o e-mail e a palavra-passe.")

# ==========================================
# SISTEMA PRINCIPAL
# ==========================================
else:
    st.title("🏆 Bolão da Galera")
    st.write(f"Olá, **{st.session_state.nome_usuario}**!")
    st.divider()

    rodada_ativa_atual = get_rodada_ativa()

    opcoes_menu = [
        "Fazer Palpites", 
        "Classificação", 
        "Meus Palpites", 
        "Campeão da Rodada",
        "Total por Rodada", 
        "Ver Palpites da Galera",
        "Resultados da Rodada",
        "Pagamento",
        "Regras e desempates"
    ]
    
    if st.session_state.is_admin:
        opcoes_menu.append("⚙️ Admin")
        
    menu = st.sidebar.selectbox("Navegação", opcoes_menu)
    
    st.sidebar.divider()
    if st.sidebar.button("🚪 Sair da Conta", use_container_width=True):
        if "sessao" in st.query_params:
            del st.query_params["sessao"]
        st.session_state.logado = False
        st.session_state.is_admin = False
        st.session_state.nome_usuario = ""
        st.session_state.email_usuario = ""
        st.rerun()

    # ------------------------------------------
    # 1. FAZER PALPITES E EDITAR
    # ------------------------------------------
    if menu == "Fazer Palpites":
        st.subheader(f"Faça ou edite os seus palpites (Rodada {rodada_ativa_atual})")
        jogos = supabase.table("jogos").select("*").eq("rodada", rodada_ativa_atual).execute().data
        
        if not jogos:
            st.info(f"Nenhum jogo registado para a rodada {rodada_ativa_atual} ainda.")
        else:
            agora = datetime.now(fuso_br)
            ids_jogos_rodada = [j['id'] for j in jogos]
            
            palpites_existentes = supabase.table("palpites").select("id_jogo, palpite").eq("nome_amigo", st.session_state.nome_usuario).in_("id_jogo", ids_jogos_rodada).execute().data
            mapa_ja_palpitou = {str(p['id_jogo']).strip(): p['palpite'] for p in palpites_existentes}
            
            jogos = ordenar_jogos_por_horario(jogos)
            
            jogos_abertos = []
            for jogo in jogos:
                if jogo.get('horario_fechamento'):
                    fechamento = converter_para_br(jogo['horario_fechamento'])
                    if agora >= fechamento: 
                        continue 
                jogos_abertos.append(jogo)

            if not jogos_abertos:
                st.success("🎉 Todos os jogos desta rodada já estão fechados (menos de 30 min para o início). Já não é possível editar palpites!")
            else:
                with st.form("form_palpites"):
                    palpites_feitos = {}
                    for jogo in jogos_abertos:
                        odd_c_texto = f" (Odd: {jogo.get('odd_casa'):.2f})" if jogo.get('odd_casa') else ""
                        odd_e_texto = f" (Odd: {jogo.get('odd_empate'):.2f})" if jogo.get('odd_empate') else ""
                        odd_f_texto = f" (Odd: {jogo.get('odd_fora'):.2f})" if jogo.get('odd_fora') else ""
                        
                        st.write(f"⚽ **{jogo['time_casa']}{odd_c_texto} x {jogo['time_fora']}{odd_f_texto}**")
                        
                        opcoes = [jogo['time_casa'], "Empate", jogo['time_fora']]
                        fechamento = converter_para_br(jogo['horario_fechamento']) if jogo.get('horario_fechamento') else None
                        
                        if fechamento:
                            hora_jogo = fechamento + timedelta(minutes=30)
                            st.caption(f"🕒 **Jogo às:** {hora_jogo.strftime('%H:%M')} | ⏳ **Fecha palpites às:** {fechamento.strftime('%H:%M')}")
                            
                        palpite_atual = mapa_ja_palpitou.get(str(jogo['id']).strip())
                        idx_atual = opcoes.index(palpite_atual) if palpite_atual in opcoes else 1
                        
                        escolha = st.selectbox("Vencedor:", opcoes, index=idx_atual, key=f"jogo_{jogo['id']}")
                        palpites_feitos[jogo['id']] = escolha
                        st.write("---")
                    
                    enviar = st.form_submit_button("Guardar Palpites", use_container_width=True)
                    
                    if enviar:
                        agora_submit = datetime.now(fuso_br)
                        salvou_algum = False
                        
                        for id_jogo, novo_palpite in palpites_feitos.items():
                            id_jogo_str = str(id_jogo).strip()
                            jogo_info = next(j for j in jogos_abertos if str(j['id']).strip() == id_jogo_str)
                            fechamento_seguro = converter_para_br(jogo_info['horario_fechamento']) if jogo_info.get('horario_fechamento') else None
                            
                            if fechamento_seguro and agora_submit >= fechamento_seguro:
                                st.error(f"⚠️ O tempo para o jogo {jogo_info['time_casa']} x {jogo_info['time_fora']} acabou enquanto preenchia! O palpite não foi aceite.")
                                continue
                                
                            if mapa_ja_palpitou.get(id_jogo_str) != novo_palpite:
                                if id_jogo_str in mapa_ja_palpitou:
                                    supabase.table("palpites").update({"palpite": novo_palpite}).eq("nome_amigo", st.session_state.nome_usuario).eq("id_jogo", id_jogo).execute()
                                else:
                                    supabase.table("palpites").insert({
                                        "nome_amigo": st.session_state.nome_usuario,
                                        "id_jogo": id_jogo,
                                        "palpite": novo_palpite
                                    }).execute()
                                salvou_algum = True
                                
                        if salvou_algum:
                            st.success("Palpites guardados/atualizados com sucesso!")
                            st.rerun()
                        else:
                            st.info("Nenhuma alteração detetada nos palpites.")

    # ------------------------------------------
    # 2. CLASSIFICAÇÃO GERAL
    # ------------------------------------------
    elif menu == "Classificação":
        st.subheader("🏆 Ranking Global")
        res_jogos_encerrados = buscar_todos_jogos_encerrados()
        res_usuarios = supabase.table("usuarios").select("nome").execute().data
        res_palpites = buscar_todos_palpites()
        
        if not res_jogos_encerrados:
            st.info("Ainda não há resultados finais lançados para contabilizar pontos.")
        else:
            df_jogos = pd.DataFrame(res_jogos_encerrados)
            df_usuarios = pd.DataFrame(res_usuarios)
            df_palpites = pd.DataFrame(res_palpites) if res_palpites else pd.DataFrame(columns=["nome_amigo", "id_jogo", "palpite"])
            
            df_usuarios['join_nome'] = df_usuarios['nome'].astype(str).str.strip().str.lower()
            df_jogos['join_id'] = df_jogos['id'].astype(str).str.strip()
            
            if not df_palpites.empty:
                df_palpites['join_nome'] = df_palpites['nome_amigo'].astype(str).str.strip().str.lower()
                df_palpites['join_id'] = df_palpites['id_jogo'].astype(str).str.strip()
                df_palpites = df_palpites.drop_duplicates(subset=['join_nome', 'join_id'], keep='last')
            else:
                df_palpites['join_nome'] = pd.Series(dtype='str')
                df_palpites['join_id'] = pd.Series(dtype='str')
            
            df_cross = df_usuarios.merge(df_jogos, how='cross')
            df_completo = df_cross.merge(df_palpites, on=['join_nome', 'join_id'], how='left')
            
            df_completo['palpite'] = df_completo['palpite'].fillna('Empate')
            df_completo['palpite_clean'] = df_completo['palpite'].astype(str).str.strip().str.lower()
            df_completo['resultado_clean'] = df_completo['resultado_real'].astype(str).str.strip().str.lower()
            df_completo['pontos'] = (df_completo['palpite_clean'] == df_completo['resultado_clean']).astype(int)
            
            df_agrupado_rodada = df_completo.groupby(['nome', 'rodada'])['pontos'].sum().reset_index()
            rodadas_com_jogos = df_jogos['rodada'].unique()
            df_rodadas_validas = df_agrupado_rodada[df_agrupado_rodada['rodada'].isin(rodadas_com_jogos)]
            
            if not df_rodadas_validas.empty:
                idx_max = df_rodadas_validas.groupby('rodada')['pontos'].transform(max) == df_rodadas_validas['pontos']
                df_campeoes = df_rodadas_validas[idx_max]
                df_titulos = df_campeoes['nome'].value_counts().reset_index()
                df_titulos.columns = ['nome', 'titulos']
            else:
                df_titulos = pd.DataFrame(columns=['nome', 'titulos'])

            df_geral = df_completo.groupby('nome')['pontos'].sum().reset_index()
            df_geral = df_geral.merge(df_titulos, on='nome', how='left')
            df_geral['titulos'] = df_geral['titulos'].fillna(0).astype(int)
            
            df_geral = df_geral.sort_values(by=['pontos', 'titulos', 'nome'], ascending=[False, False, True]).reset_index(drop=True)
            df_geral.index += 1
            df_geral.columns = ["Participante", "Total de Pontos", "Títulos (Desempate)"]
            st.table(df_geral)

    # ------------------------------------------
    # 3. MEUS PALPITES 
    # ------------------------------------------
    elif menu == "Meus Palpites":
        st.subheader("Os Meus Palpites")
        rodada = st.number_input("Filtrar por Rodada", min_value=1, step=1, value=rodada_ativa_atual, key="rod_meus")
        jogos = supabase.table("jogos").select("*").eq("rodada", rodada).execute().data
        
        if jogos:
            ids_jogos = [j['id'] for j in jogos]
            meus_palpites = []
            if ids_jogos:
                meus_palpites = supabase.table("palpites").select("*").eq("nome_amigo", st.session_state.nome_usuario).in_("id_jogo", ids_jogos).execute().data
            
            jogos = ordenar_jogos_por_horario(jogos)
            agora = datetime.now(fuso_br)
            
            mapa_meus = {str(p['id_jogo']).strip(): p['palpite'] for p in meus_palpites}
            dados_view = []
            
            for jogo in jogos:
                partida = f"{jogo['time_casa']} x {jogo['time_fora']}"
                res_real = jogo.get("resultado_real") or "A aguardar..."
                fechamento = converter_para_br(jogo['horario_fechamento']) if jogo.get('horario_fechamento') else None
                jogo_fechado = fechamento and agora >= fechamento
                palpite_feito = mapa_meus.get(str(jogo['id']).strip())
                
                if palpite_feito:
                    palpite_mostrar = palpite_feito
                else:
                    palpite_mostrar = "Empate (Auto)" if jogo_fechado else "Pendente"
                        
                dados_view.append({"Partida": partida, "O Meu Palpite": palpite_mostrar, "Resultado Real": res_real})
                
            df_view = pd.DataFrame(dados_view)
            st.table(df_view.set_index("Partida"))
        else:
            st.info("Nenhum jogo nesta rodada.")

    # ------------------------------------------
    # 4. CAMPEÃO DA RODADA
    # ------------------------------------------
    elif menu == "Campeão da Rodada":
        st.subheader("👑 Campeões por Rodada")
        res_jogos = buscar_todos_jogos_encerrados()
        res_usuarios = supabase.table("usuarios").select("nome").execute().data
        res_palpites = buscar_todos_palpites()
        
        if not res_jogos:
            st.info("Ainda não há jogos finalizados para determinar campeões.")
        else:
            df_jogos = pd.DataFrame(res_jogos)
            df_usuarios = pd.DataFrame(res_usuarios)
            df_palpites = pd.DataFrame(res_palpites) if res_palpites else pd.DataFrame(columns=["nome_amigo", "id_jogo", "palpite"])
            
            df_usuarios['join_nome'] = df_usuarios['nome'].astype(str).str.strip().str.lower()
            df_jogos['join_id'] = df_jogos['id'].astype(str).str.strip()
            
            if not df_palpites.empty:
                df_palpites['join_nome'] = df_palpites['nome_amigo'].astype(str).str.strip().str.lower()
                df_palpites['join_id'] = df_palpites['id_jogo'].astype(str).str.strip()
                df_palpites = df_palpites.drop_duplicates(subset=['join_nome', 'join_id'], keep='last')
            else:
                df_palpites['join_nome'] = pd.Series(dtype='str')
                df_palpites['join_id'] = pd.Series(dtype='str')
            
            df_cross = df_usuarios.merge(df_jogos, how='cross')
            df_completo = df_cross.merge(df_palpites, on=['join_nome', 'join_id'], how='left')
            df_completo['palpite'] = df_completo['palpite'].fillna('Empate')
            df_completo['palpite_clean'] = df_completo['palpite'].astype(str).str.strip().str.lower()
            df_completo['resultado_clean'] = df_completo['resultado_real'].astype(str).str.strip().str.lower()
            df_completo['pontos'] = (df_completo['palpite_clean'] == df_completo['resultado_clean']).astype(int)
            
            df_agrupado_rodada = df_completo.groupby(['nome', 'rodada'])['pontos'].sum().reset_index()
            rodadas_com_jogos = df_jogos['rodada'].unique()
            df_rodadas_validas = df_agrupado_rodada[df_agrupado_rodada['rodada'].isin(rodadas_com_jogos)]
            
            if not df_rodadas_validas.empty:
                idx_max = df_rodadas_validas.groupby('rodada')['pontos'].transform(max) == df_rodadas_validas['pontos']
                df_campeoes = df_rodadas_validas[idx_max]
                
                col1, col2 = st.columns([1, 1])
                with col1:
                    st.write("🏆 **Ranking de Vitórias**")
                    ranking_vitorias = df_campeoes['nome'].value_counts().reset_index()
                    ranking_vitorias.columns = ["Participante", "Qtd. Rodadas Ganhas"]
                    st.table(ranking_vitorias.set_index("Participante"))
                
                with col2:
                    st.write("🔎 **Consultar Vencedor por Rodada**")
                    rodadas_disponiveis = sorted(df_campeoes['rodada'].unique())
                    rodada_selecionada = st.selectbox("Escolha a Rodada", rodadas_disponiveis)
                    vencedores_desta_rodada = df_campeoes[df_campeoes['rodada'] == rodada_selecionada]
                    vencedores_desta_rodada = vencedores_desta_rodada[['nome', 'pontos']].rename(columns={"nome": "Campeão(ões)", "pontos": "Pontos Feitos"})
                    st.table(vencedores_desta_rodada.set_index("Campeão(ões)"))
            else:
                st.info("Nenhum palpite registado ainda.")

    # ------------------------------------------
    # 5. TOTAL POR RODADA
    # ------------------------------------------
    elif menu == "Total por Rodada":
        st.subheader("📊 Pontos Detalhados por Rodada")
        res_jogos_encerrados = buscar_todos_jogos_encerrados()
        res_usuarios = supabase.table("usuarios").select("nome").execute().data
        res_palpites = buscar_todos_palpites()
        
        if not res_jogos_encerrados:
            st.info("Ainda não há resultados finais lançados para contabilizar pontos.")
        else:
            df_jogos = pd.DataFrame(res_jogos_encerrados)
            df_usuarios = pd.DataFrame(res_usuarios)
            df_palpites = pd.DataFrame(res_palpites) if res_palpites else pd.DataFrame(columns=["nome_amigo", "id_jogo", "palpite"])
            
            df_usuarios['join_nome'] = df_usuarios['nome'].astype(str).str.strip().str.lower()
            df_jogos['join_id'] = df_jogos['id'].astype(str).str.strip()
            
            if not df_palpites.empty:
                df_palpites['join_nome'] = df_palpites['nome_amigo'].astype(str).str.strip().str.lower()
                df_palpites['join_id'] = df_palpites['id_jogo'].astype(str).str.strip()
                df_palpites = df_palpites.drop_duplicates(subset=['join_nome', 'join_id'], keep='last')
            else:
                df_palpites['join_nome'] = pd.Series(dtype='str')
                df_palpites['join_id'] = pd.Series(dtype='str')
            
            df_cross = df_usuarios.merge(df_jogos, how='cross')
            df_completo = df_cross.merge(df_palpites, on=['join_nome', 'join_id'], how='left')
            
            df_completo['palpite'] = df_completo['palpite'].fillna('Empate')
            df_completo['palpite_clean'] = df_completo['palpite'].astype(str).str.strip().str.lower()
            df_completo['resultado_clean'] = df_completo['resultado_real'].astype(str).str.strip().str.lower()
            df_completo['pontos'] = (df_completo['palpite_clean'] == df_completo['resultado_clean']).astype(int)
            
            df_agrupado = df_completo.groupby(['nome', 'rodada'])['pontos'].sum().reset_index()
            rodadas_com_jogos = df_jogos['rodada'].unique()
            df_rodadas_validas = df_agrupado[df_agrupado['rodada'].isin(rodadas_com_jogos)]
            
            if not df_rodadas_validas.empty:
                idx_max = df_rodadas_validas.groupby('rodada')['pontos'].transform(max) == df_rodadas_validas['pontos']
                df_titulos = df_rodadas_validas[idx_max]['nome'].value_counts().reset_index()
                df_titulos.columns = ['nome', 'titulos']
            else:
                df_titulos = pd.DataFrame(columns=['nome', 'titulos'])
            
            df_pivot = df_agrupado.pivot(index='nome', columns='rodada', values='pontos').fillna(0).astype(int)
            df_pivot.columns = [f"Rodada {col}" for col in df_pivot.columns]
            df_pivot['Total'] = df_pivot.sum(axis=1)
            
            df_temp = df_pivot.reset_index().merge(df_titulos, on='nome', how='left')
            df_temp['titulos'] = df_temp['titulos'].fillna(0).astype(int)
            df_temp = df_temp.sort_values(by=['Total', 'titulos', 'nome'], ascending=[False, False, True])
            df_pivot = df_temp.drop(columns=['titulos']).set_index('nome')
            
            altura_tabela = (len(df_pivot) + 1) * 36 + 3
            st.dataframe(df_pivot, height=altura_tabela, use_container_width=True)

    # ------------------------------------------
    # 6. VER PALPITES DA GALERA
    # ------------------------------------------
    elif menu == "Ver Palpites da Galera":
        st.subheader("Quem apostou no quê?")
        rodada = st.number_input("Rodada", min_value=1, step=1, value=rodada_ativa_atual)
        jogos = supabase.table("jogos").select("*").eq("rodada", rodada).execute().data
        usuarios = supabase.table("usuarios").select("nome").execute().data
        
        nomes_usuarios = [u['nome'] for u in usuarios]
        agora = datetime.now(fuso_br)
        
        if jogos:
            jogos = ordenar_jogos_por_horario(jogos)
            ids_jogos = [j['id'] for j in jogos]
            ordem_cronologica_partidas = [f"{j['time_casa']} x {j['time_fora']}" for j in jogos]
            
            palpites = buscar_todos_palpites(filtro_ids_jogos=ids_jogos)
            
            mapa_palpites = {}
            for p in palpites:
                chave = (str(p['id_jogo']).strip(), str(p['nome_amigo']).strip().lower())
                mapa_palpites[chave] = p['palpite']
                
            dados_tabela = []
            
            for jogo in jogos:
                partida = f"{jogo['time_casa']} x {jogo['time_fora']}"
                fechamento = converter_para_br(jogo['horario_fechamento']) if jogo.get('horario_fechamento') else None
                passou_do_tempo = fechamento and agora >= fechamento
                jogo_liberado = passou_do_tempo
                
                for nome in nomes_usuarios:
                    palpite_real = mapa_palpites.get((str(jogo['id']).strip(), str(nome).strip().lower()))
                    if palpite_real:
                        palpite_visivel = palpite_real if jogo_liberado else "🔒 Oculto"
                    else:
                        palpite_visivel = "Empate (Auto)" if passou_do_tempo else "Pendente"
                        
                    dados_tabela.append({"Nome": nome, "Partida": partida, "Palpite": palpite_visivel})
                    
            df_completo = pd.DataFrame(dados_tabela)
            tabela = df_completo.pivot_table(index="Nome", columns="Partida", values="Palpite", aggfunc='first')
            
            colunas_existentes = [p for p in ordem_cronologica_partidas if p in tabela.columns]
            tabela = tabela[colunas_existentes]
            
            altura_tabela = (len(tabela) + 1) * 36 + 3
            st.dataframe(tabela, height=altura_tabela, use_container_width=True)
        else:
            st.info("Sem dados para exibir.")

    # ------------------------------------------
    # 7. RESULTADOS DA RODADA
    # ------------------------------------------
    elif menu == "Resultados da Rodada":
        st.subheader("🏁 Resultados Oficiais")
        rodada = st.number_input("Selecione a Rodada", min_value=1, step=1, value=rodada_ativa_atual)
        jogos = supabase.table("jogos").select("*").eq("rodada", rodada).execute().data
        
        if jogos:
            jogos = ordenar_jogos_por_horario(jogos)
            dados_view = []
            for jogo in jogos:
                partida = f"{jogo['time_casa']} x {jogo['time_fora']}"
                res_real = jogo.get("resultado_real")
                status = res_real if res_real else "⏳ A aguardar resultado"
                dados_view.append({"Partida": partida, "Vencedor Oficial": status})
                
            df_view = pd.DataFrame(dados_view)
            st.table(df_view.set_index("Partida"))
        else:
            st.info("Nenhum jogo registado para esta rodada.")

    # ------------------------------------------
    # 8. PAGAMENTO
    # ------------------------------------------
    elif menu == "Pagamento":
        st.subheader("💰 Controlo de Pagamento Mensal")
        st.write("Acompanhe o estado das mensalidades (X = Pago).")
        res_pagamentos = supabase.table("pagamentos").select("*").limit(10000).execute().data
        
        if res_pagamentos:
            df_pag = pd.DataFrame(res_pagamentos)
            colunas_map = {
                "nome": "Participantes", "m02": "02/2026", "m03": "03/2026", "m04": "04/2026",
                "m05": "05/2026", "m06": "06/2026", "m07": "07/2026", "m08": "08/2026",
                "m09": "09/2026", "m10": "10/2026", "m11": "11/2026", "m12": "12/2026"
            }
            df_pag = df_pag.rename(columns=colunas_map)
            df_pag = df_pag.sort_values(by="Participantes").reset_index(drop=True)
            
            altura_tabela = (len(df_pag) + 1) * 36 + 3
            st.dataframe(df_pag.set_index("Participantes"), height=altura_tabela, use_container_width=True)
        else:
            st.info("Ainda não existem registos de pagamento na base de dados. O Administrador precisa de inicializar a tabela.")

    # ------------------------------------------
    # 9. REGRAS E DESEMPATES
    # ------------------------------------------
    elif menu == "Regras e desempates":
        st.subheader("⚖️ Regras e Critérios de Desempate")
        st.markdown("""
        **🏆 Campeão da Rodada** O Campeão da Rodada é aquele que obtiver a maior soma de pontos apenas nos jogos correspondentes àquela rodada específica.  
        Se houver empate no número máximo de pontos, todos os empatados são considerados "Campeões" daquela rodada.

        **🥇 Classificação Geral (Critérios de Desempate)** Em caso de empate na pontuação total do Bolão, a ordem na tabela classificativa é definida pelos seguintes critérios:  
        1. **Maior número de pontos gerais** (1 Ponto por cada vencedor acertado ou empate).  
        2. **Maior quantidade de campeões da rodada.**

        **⏳ Limite de Palpites** * Os palpites podem ser inseridos ou alterados até **exatamente 30 minutos antes** do horário oficial de início da partida.  
        * Após esse limite, o jogo é bloqueado. Se não tiver deixado palpite, o sistema assumirá "Empate" automaticamente.  
        * Assim que o jogo bloqueia, os palpites ficam públicos para todos verem.
        """)

    # ------------------------------------------
    # 10. ADMIN
    # ------------------------------------------
    elif menu == "⚙️ Admin":
        aba1, aba2, aba_odds, aba_fin, aba_resumo, aba3, aba4 = st.tabs([
            "Partidas", "Resultados", "📈 Odds", "💲 Financeiro", "📊 Resumo", "Relatórios", "Pagamentos"
        ])
        
        with aba1:
            st.subheader("1. Definir Rodada Ativa")
            nova_rodada_ativa = st.number_input("Qual a rodada atual do bolão?", min_value=1, step=1, value=rodada_ativa_atual)
            if st.button("Atualizar Rodada Ativa", use_container_width=True):
                supabase.table("configuracoes").upsert({"id": 1, "rodada_ativa": nova_rodada_ativa}).execute()
                st.success(f"Rodada ativa alterada para {nova_rodada_ativa}!")
                st.rerun()

            st.divider()

            st.subheader("2. Registar Novo Jogo")
            rod_novo_jogo = st.number_input("Escolha a Rodada para registar o jogo", min_value=1, step=1, value=rodada_ativa_atual, key="rod_reg")
            
            jogos_cadastrados_nesta_rodada = supabase.table("jogos").select("time_casa, time_fora").eq("rodada", rod_novo_jogo).limit(10000).execute().data
            times_ja_jogando = []
            for j in jogos_cadastrados_nesta_rodada:
                times_ja_jogando.extend([j['time_casa'], j['time_fora']])
            
            times_disponiveis = [t for t in TIMES_SERIE_A if t not in times_ja_jogando]
            
            if len(times_disponiveis) >= 2:
                with st.form("novo_jogo"):
                    col1, col2 = st.columns(2)
                    casa = col1.selectbox("Visitado (Casa)", times_disponiveis)
                    fora = col2.selectbox("Visitante (Fora)", times_disponiveis, index=1 if len(times_disponiveis) > 1 else 0)
                    
                    col4, col5 = st.columns(2)
                    data_jogo = col4.date_input("Data do Jogo")
                    hora_jogo = col5.time_input("Hora do Jogo", value=time(16, 0)) 
                    
                    if st.form_submit_button("Registar Partida", use_container_width=True):
                        if casa == fora:
                            st.error("O time de Casa e de Fora não podem ser o mesmo!")
                        else:
                            dt_jogo = fuso_br.localize(datetime.combine(data_jogo, hora_jogo))
                            dt_fechamento = dt_jogo - timedelta(minutes=30)
                            
                            supabase.table("jogos").insert({
                                "rodada": rod_novo_jogo, 
                                "time_casa": casa, 
                                "time_fora": fora,
                                "horario_fechamento": dt_fechamento.isoformat()
                            }).execute()
                            
                            st.success(f"Jogo {casa} x {fora} registado com sucesso!")
                            st.rerun()
            else:
                st.info("⚽ Todos os times da Série A já estão alocados para esta rodada (10 jogos completos)!")
        
        with aba2:
            st.subheader("Lançar / Editar Resultado Final")
            rod_resultado = st.number_input("Filtrar por Rodada", min_value=1, step=1, value=rodada_ativa_atual, key="rod_res")
            jogos_rodada = supabase.table("jogos").select("*").eq("rodada", rod_resultado).limit(10000).execute().data
            
            if jogos_rodada:
                jogos_rodada = ordenar_jogos_por_horario(jogos_rodada)
                for jogo in jogos_rodada:
                    res_atual = jogo.get("resultado_real")
                    opcoes = [jogo['time_casa'], "Empate", jogo['time_fora']]
                    
                    if res_atual:
                        st.success(f"✅ **{jogo['time_casa']} x {jogo['time_fora']}**")
                        st.caption(f"Status: Resultado já lançado (**{res_atual}**)")
                        idx_atual = opcoes.index(res_atual) if res_atual in opcoes else 1
                        vencedor = st.selectbox("Alterar resultado para:", opcoes, index=idx_atual, key=f"res_{jogo['id']}")
                        texto_botao = "✏️ Editar Resultado"
                    else:
                        st.info(f"⏳ **{jogo['time_casa']} x {jogo['time_fora']}**")
                        st.caption("Status: A aguardar resultado oficial")
                        vencedor = st.selectbox("Quem ganhou?", opcoes, index=1, key=f"res_{jogo['id']}")
                        texto_botao = "💾 Guardar Resultado"
                    
                    if st.button(texto_botao, key=f"btn_{jogo['id']}", use_container_width=True):
                        supabase.table("jogos").update({"resultado_real": vencedor}).eq("id", jogo["id"]).execute()
                        st.success("Resultado guardado e classificação recalculada com sucesso!")
                        st.rerun()
                    st.write("---")
            else:
                st.write("Nenhum jogo registado para esta rodada.")

        with aba_odds:
            st.subheader("📈 Lançar / Editar Odds da Rodada")
            rod_odds = st.number_input("Filtrar por Rodada", min_value=1, step=1, value=rodada_ativa_atual, key="rod_odds")
            jogos_odds = supabase.table("jogos").select("*").eq("rodada", rod_odds).limit(10000).execute().data
            
            if jogos_odds:
                jogos_odds = ordenar_jogos_por_horario(jogos_odds)
                
                with st.form(f"form_odds_{rod_odds}"):
                    odds_atualizadas = {}
                    for jogo in jogos_odds:
                        st.write(f"⚽ **{jogo['time_casa']} x {jogo['time_fora']}**")
                        
                        col_c, col_e, col_f = st.columns(3)
                        val_c = float(jogo.get('odd_casa') or 1.00)
                        val_e = float(jogo.get('odd_empate') or 1.00)
                        val_f = float(jogo.get('odd_fora') or 1.00)
                        
                        odd_c = col_c.number_input(f"Casa ({jogo['time_casa']})", min_value=1.0, step=0.01, value=val_c, format="%.2f", key=f"odd_c_{jogo['id']}")
                        odd_e = col_e.number_input("Empate", min_value=1.0, step=0.01, value=val_e, format="%.2f", key=f"odd_e_{jogo['id']}")
                        odd_f = col_f.number_input(f"Fora ({jogo['time_fora']})", min_value=1.0, step=0.01, value=val_f, format="%.2f", key=f"odd_f_{jogo['id']}")
                        
                        odds_atualizadas[jogo['id']] = {"odd_casa": odd_c, "odd_empate": odd_e, "odd_fora": odd_f}
                        st.write("---")
                    
                    if st.form_submit_button("💾 Salvar Todas as Odds", use_container_width=True):
                        for id_j, odds in odds_atualizadas.items():
                            supabase.table("jogos").update({
                                "odd_casa": odds["odd_casa"],
                                "odd_empate": odds["odd_empate"],
                                "odd_fora": odds["odd_fora"]
                            }).eq("id", id_j).execute()
                        st.success("Odds da rodada salvas com sucesso!")
                        st.rerun()
            else:
                st.write("Nenhum jogo registado para esta rodada.")

        with aba_fin:
            st.subheader("💲 Projeção e Resultado Financeiro")
            rod_fin = st.number_input("Escolha a Rodada", min_value=1, step=1, value=rodada_ativa_atual, key="rod_fin")
            
            usuarios_fin = supabase.table("usuarios").select("id").execute().data
            total_participantes = len(usuarios_fin) if usuarios_fin else 1
            
            valor_total_jogo = st.number_input("Valor Total Arrecadado por Jogo (R$):", min_value=1.0, value=110.0, step=10.0, key="cfg_fin_valor")
            valor_aposta = valor_total_jogo / total_participantes
            
            st.caption(f"ℹ️ Baseado em {total_participantes} participantes, cada palpite equivale a **R$ {valor_aposta:.2f}**.")
            
            jogos_fin = supabase.table("jogos").select("*").eq("rodada", rod_fin).limit(10000).execute().data
            
            if jogos_fin:
                jogos_fin = ordenar_jogos_por_horario(jogos_fin)
                ids_jogos_fin = [j['id'] for j in jogos_fin]
                
                palpites_brutos = buscar_todos_palpites(filtro_ids_jogos=ids_jogos_fin)
                df_palp_fin = pd.DataFrame(palpites_brutos) if palpites_brutos else pd.DataFrame(columns=['id_jogo', 'nome_amigo', 'palpite'])
                
                if not df_palp_fin.empty:
                    df_palp_fin['join_nome'] = df_palp_fin['nome_amigo'].astype(str).str.strip().str.lower()
                    df_palp_fin['join_id'] = df_palp_fin['id_jogo'].astype(str).str.strip()
                    df_palp_fin = df_palp_fin.drop_duplicates(subset=['join_nome', 'join_id'], keep='last')
                    palpites_fin = df_palp_fin.to_dict('records')
                else:
                    palpites_fin = []
                
                for jogo in jogos_fin:
                    st.write(f"### ⚽ {jogo['time_casa']} x {jogo['time_fora']}")
                    
                    odd_c = float(jogo.get('odd_casa') or 1.0)
                    odd_e = float(jogo.get('odd_empate') or 1.0)
                    odd_f = float(jogo.get('odd_fora') or 1.0)
                    
                    qtd_c = sum(1 for p in palpites_fin if str(p['id_jogo']) == str(jogo['id']) and p['palpite'] == jogo['time_casa'])
                    qtd_e = sum(1 for p in palpites_fin if str(p['id_jogo']) == str(jogo['id']) and (p['palpite'] == 'Empate' or 'Empate' in p['palpite']))
                    qtd_f = sum(1 for p in palpites_fin if str(p['id_jogo']) == str(jogo['id']) and p['palpite'] == jogo['time_fora'])
                    
                    vol_c = qtd_c * valor_aposta
                    vol_e = qtd_e * valor_aposta
                    vol_f = qtd_f * valor_aposta
                    
                    if jogo.get('resultado_real'):
                        res_real = jogo['resultado_real']
                        st.success(f"✅ **Resultado Oficial: {res_real}**")
                        
                        if res_real == jogo['time_casa']:
                            val_ganhador = vol_c * odd_c
                            val_p1 = -vol_e
                            val_p2 = -vol_f
                            texto_v = f"✅ {jogo['time_casa']}: R$ {val_ganhador:.2f}"
                            texto_p1 = f"❌ Empate: -R$ {abs(val_p1):.2f}"
                            texto_p2 = f"❌ {jogo['time_fora']}: -R$ {abs(val_p2):.2f}"
                        elif res_real == 'Empate' or res_real == 'Empate (Auto)':
                            val_ganhador = vol_e * odd_e
                            val_p1 = -vol_c
                            val_p2 = -vol_f
                            texto_v = f"✅ Empate: R$ {val_ganhador:.2f}"
                            texto_p1 = f"❌ {jogo['time_casa']}: -R$ {abs(val_p1):.2f}"
                            texto_p2 = f"❌ {jogo['time_fora']}: -R$ {abs(val_p2):.2f}"
                        else:
                            val_ganhador = vol_f * odd_f
                            val_p1 = -vol_c
                            val_p2 = -vol_e
                            texto_v = f"✅ {jogo['time_fora']}: R$ {val_ganhador:.2f}"
                            texto_p1 = f"❌ {jogo['time_casa']}: -R$ {abs(val_p1):.2f}"
                            texto_p2 = f"❌ Empate: -R$ {abs(val_p2):.2f}"
                            
                        valor_jogo = val_ganhador + val_p1 + val_p2
                        
                        st.write(texto_v)
                        st.write(texto_p1)
                        st.write(texto_p2)
                        st.markdown(f"**➖ Valor do Jogo (Soma): <span style='font-size:18px;'>R$ {valor_jogo:.2f}</span>**", unsafe_allow_html=True)
                        
                    else:
                        st.write("**Projeção do Valor do Jogo (Se o resultado for...):**")
                        df_proj = pd.DataFrame({
                            "Se Resultado For:": [f"{jogo['time_casa']}", "Empate", f"{jogo['time_fora']}"],
                            "Valor do Jogo (Soma)": [
                                f"R$ {((vol_c * odd_c) - vol_e - vol_f):.2f}",
                                f"R$ {((vol_e * odd_e) - vol_c - vol_f):.2f}",
                                f"R$ {((vol_f * odd_f) - vol_c - vol_e):.2f}"
                            ]
                        })
                        st.table(df_proj.set_index("Se Resultado For:"))
                        
                    st.divider()
            else:
                st.info("Nenhum jogo registado para esta rodada.")

        with aba_resumo:
            st.subheader("📊 Resumo Financeiro (Valor dos Jogos Encerrados)")
            
            usuarios_res = supabase.table("usuarios").select("id").execute().data
            tot_part_res = len(usuarios_res) if usuarios_res else 1
            valor_tot_jogo_res = st.number_input("Valor Total Arrecadado por Jogo (R$):", min_value=1.0, value=110.0, step=10.0, key="cfg_resumo_valor")
            val_aposta = valor_tot_jogo_res / tot_part_res
            
            jogos_encerrados = buscar_todos_jogos_encerrados()
            
            if not jogos_encerrados:
                st.info("Ainda não existem resultados finais lançados para calcular o resumo.")
            else:
                ids_jogos_encerrados = [j['id'] for j in jogos_encerrados]
                palp_res_brutos = buscar_todos_palpites(filtro_ids_jogos=ids_jogos_encerrados)
                
                df_palp_res = pd.DataFrame(palp_res_brutos) if palp_res_brutos else pd.DataFrame(columns=['id_jogo', 'nome_amigo', 'palpite'])
                if not df_palp_res.empty:
                    df_palp_res['join_nome'] = df_palp_res['nome_amigo'].astype(str).str.strip().str.lower()
                    df_palp_res['join_id'] = df_palp_res['id_jogo'].astype(str).str.strip()
                    df_palp_res = df_palp_res.drop_duplicates(subset=['join_nome', 'join_id'], keep='last')
                    palpites_res = df_palp_res.to_dict('records')
                else:
                    palpites_res = []

                resumo_rodadas = {}
                
                for jogo in jogos_encerrados:
                    rodada = jogo['rodada']
                    if rodada not in resumo_rodadas:
                        resumo_rodadas[rodada] = {"valor_rodada": 0.0}
                    
                    res_real = jogo['resultado_real']
                    odd_c = float(jogo.get('odd_casa') or 1.0)
                    odd_e = float(jogo.get('odd_empate') or 1.0)
                    odd_f = float(jogo.get('odd_fora') or 1.0)
                    
                    qtd_c = sum(1 for p in palpites_res if str(p['id_jogo']) == str(jogo['id']) and p['palpite'] == jogo['time_casa'])
                    qtd_e = sum(1 for p in palpites_res if str(p['id_jogo']) == str(jogo['id']) and (p['palpite'] == 'Empate' or 'Empate' in p['palpite']))
                    qtd_f = sum(1 for p in palpites_res if str(p['id_jogo']) == str(jogo['id']) and p['palpite'] == jogo['time_fora'])
                    
                    vol_c = qtd_c * val_aposta
                    vol_e = qtd_e * val_aposta
                    vol_f = qtd_f * val_aposta
                    
                    valor_jogo_neste = 0.0
                    if res_real == jogo['time_casa']:
                        valor_jogo_neste = (vol_c * odd_c) - vol_e - vol_f
                    elif res_real == 'Empate' or res_real == 'Empate (Auto)':
                        valor_jogo_neste = (vol_e * odd_e) - vol_c - vol_f
                    elif res_real == jogo['time_fora']:
                        valor_jogo_neste = (vol_f * odd_f) - vol_c - vol_e
                        
                    resumo_rodadas[rodada]["valor_rodada"] += valor_jogo_neste

                tabela_resumo = []
                total_geral = 0.0
                
                for r in sorted(resumo_rodadas.keys()):
                    valor = resumo_rodadas[r]["valor_rodada"]
                    total_geral += valor
                    tabela_resumo.append({
                        "Rodada": f"Rodada {r}",
                        "Valor da Rodada": f"R$ {valor:.2f}"
                    })
                
                tabela_resumo.append({
                    "Rodada": "TOTAL GERAL",
                    "Valor da Rodada": f"R$ {total_geral:.2f}"
                })
                
                df_res_view = pd.DataFrame(tabela_resumo)
                st.table(df_res_view.set_index("Rodada"))

        with aba3:
            st.subheader("📱 Gerador de Relatórios WhatsApp")
            st.write(f"Estes relatórios baseiam-se na **Rodada {rodada_ativa_atual} (Ativa)**.")
            jogos_ativos = supabase.table("jogos").select("*").eq("rodada", rodada_ativa_atual).limit(10000).execute().data
            
            if not jogos_ativos:
                st.warning("Não há jogos registados na rodada ativa para gerar relatórios.")
            else:
                if st.button("📋 Gerar Relatório de Faltosos", use_container_width=True):
                    todos_usuarios = supabase.table("usuarios").select("nome").execute().data
                    nomes_todos = [u['nome'] for u in todos_usuarios]
                    ids_jogos = [j['id'] for j in jogos_ativos]
                    
                    palpites_feitos = buscar_todos_palpites(filtro_ids_jogos=ids_jogos)
                        
                    nomes_votaram = set([p['nome_amigo'] for p in palpites_feitos])
                    faltosos = [nome for nome in nomes_todos if nome not in nomes_votaram]
                    
                    if faltosos:
                        msg = f"🚨 *Atenção, galera!* 🚨\nFaltam fazer os palpites da Rodada {rodada_ativa_atual}:\n\n"
                        for f in faltosos:
                            msg += f"👉 {f}\n"
                        msg += "\nCorram antes que os jogos fechem! ⏰"
                        st.info("Copie a mensagem abaixo:")
                        st.code(msg, language="text")
                    else:
                        st.success("🎉 Todos os utilizadores já fizeram palpites nesta rodada!")
                
                if st.button("⚽ Gerar Agenda de Jogos", use_container_width=True):
                    jogos_ativos_ordenados = ordenar_jogos_por_horario(jogos_ativos)
                    msg = f"🏆 *Agenda da Rodada {rodada_ativa_atual}*\n\n"
                    for j in jogos_ativos_ordenados:
                        fechamento = converter_para_br(j['horario_fechamento'])
                        hora_jogo = fechamento + timedelta(minutes=30)
                        msg += f"⚽ {j['time_casa']} x {j['time_fora']}\n"
                        msg += f"⏰ Jogo: {hora_jogo.strftime('%d/%m às %H:%M')}\n"
                        msg += f"🔒 Palpites encerram: {fechamento.strftime('%H:%M')}\n\n"
                    st.info("Copie a mensagem abaixo:")
                    st.code(msg, language="text")
        
        with aba4:
            st.subheader("💰 Gestor de Pagamentos")
            st.write("Edite diretamente a tabela abaixo. Pressione ENTER para guardar e depois clique em 'Salvar no Banco'. Digite 'X' para confirmar pago.")
            usuarios = supabase.table("usuarios").select("nome").execute().data
            pagamentos = supabase.table("pagamentos").select("*").limit(10000).execute().data
            
            nomes_usuarios = [u['nome'] for u in usuarios]
            nomes_pagamentos = [p['nome'] for p in pagamentos]
            
            novos = [n for n in nomes_usuarios if n not in nomes_pagamentos]
            for novo in novos:
                supabase.table("pagamentos").insert({"nome": novo}).execute()
            
            pagamentos_atuais = supabase.table("pagamentos").select("*").limit(10000).execute().data
            if pagamentos_atuais:
                df_pagamentos = pd.DataFrame(pagamentos_atuais)
                df_pagamentos = df_pagamentos.sort_values(by="nome").reset_index(drop=True)
                
                altura_tabela = (len(df_pagamentos) + 1) * 36 + 3
                tabela_editada = st.data_editor(
                    df_pagamentos,
                    height=altura_tabela,
                    column_config={
                        "nome": st.column_config.TextColumn("Participantes", disabled=True),
                        "m02": "02/2026", "m03": "03/2026", "m04": "04/2026", "m05": "05/2026",
                        "m06": "06/2026", "m07": "07/2026", "m08": "08/2026", "m09": "09/2026",
                        "m10": "10/2026", "m11": "11/2026", "m12": "12/2026"
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
                if st.button("💾 Salvar Pagamentos no Banco", use_container_width=True):
                    for index, row in tabela_editada.iterrows():
                        supabase.table("pagamentos").update({
                            "m02": row["m02"], "m03": row["m03"], "m04": row["m04"],
                            "m05": row["m05"], "m06": row["m06"], "m07": row["m07"],
                            "m08": row["m08"], "m09": row["m09"], "m10": row["m10"],
                            "m11": row["m11"], "m12": row["m12"]
                        }).eq("nome", row["nome"]).execute()
                    st.success("Tabela de pagamentos atualizada com sucesso!")