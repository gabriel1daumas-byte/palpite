import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, time, timedelta
import pytz
import base64

# --- CONFIGURAÇÃO INICIAL E CONEXÃO ---
st.set_page_config(page_title="Bolão da Galera", page_icon="🏆", layout="wide")

# Truque de CSS para forçar o Combo (Selectbox) a mostrar todos os itens sem scroll
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

# --- FUNÇÕES PARA PROTEGER A SESSÃO NA URL ---
def codificar_sessao(email):
    return base64.b64encode(email.encode()).decode()

def decodificar_sessao(codigo):
    try:
        return base64.b64decode(codigo.encode()).decode()
    except:
        return None

# --- CONTROLO DE SESSÃO À PROVA DE F5 ---
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.nome_usuario = ""
    st.session_state.email_usuario = ""
    st.session_state.is_admin = False

# Lê a URL imediatamente após o F5
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
# ECRÃ DE ACESSO (LOGIN UNIFICADO)
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

    # Ordem exata solicitada
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
            mapa_ja_palpitou = {p['id_jogo']: p['palpite'] for p in palpites_existentes}
            
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
                        st.write(f"⚽ **{jogo['time_casa']} x {jogo['time_fora']}**")
                        
                        opcoes = [jogo['time_casa'], "Empate", jogo['time_fora']]
                        fechamento = converter_para_br(jogo['horario_fechamento']) if jogo.get('horario_fechamento') else None
                        
                        if fechamento:
                            hora_jogo = fechamento + timedelta(minutes=30)
                            st.caption(f"🕒 **Jogo às:** {hora_jogo.strftime('%H:%M')} | ⏳ **Fecha palpites às:** {fechamento.strftime('%H:%M')}")
                            
                        palpite_atual = mapa_ja_palpitou.get(jogo['id'])
                        idx_atual = opcoes.index(palpite_atual) if palpite_atual in opcoes else 1
                            
                        escolha = st.selectbox("Vencedor:", opcoes, index=idx_atual, key=f"jogo_{jogo['id']}")
                        palpites_feitos[jogo['id']] = escolha
                        
                        st.write("---")
                    
                    enviar = st.form_submit_button("Guardar Palpites", use_container_width=True)
                    
                    if enviar:
                        agora_submit = datetime.now(fuso_br)
                        salvou_algum = False
                        
                        for id_jogo, novo_palpite in palpites_feitos.items():
                            jogo_info = next(j for j in jogos_abertos if j['id'] == id_jogo)
                            fechamento_seguro = converter_para_br(jogo_info['horario_fechamento']) if jogo_info.get('horario_fechamento') else None
                            
                            if fechamento_seguro and agora_submit >= fechamento_seguro:
                                st.error(f"⚠️ O tempo para o jogo {jogo_info['time_casa']} x {jogo_info['time_fora']} acabou enquanto preenchia! O palpite não foi aceite.")
                                continue
                                
                            if mapa_ja_palpitou.get(id_jogo) != novo_palpite:
                                if id_jogo in mapa_ja_palpitou:
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
        
        res_jogos_encerrados = supabase.table("jogos").select("id, rodada, resultado_real").not_.is_("resultado_real", "null").execute()
        res_usuarios = supabase.table("usuarios").select("nome").execute()
        res_palpites = supabase.table("palpites").select("nome_amigo, id_jogo, palpite").execute()
        
        if not res_jogos_encerrados.data:
            st.info("Ainda não há resultados finais lançados para contabilizar pontos.")
        else:
            df_jogos = pd.DataFrame(res_jogos_encerrados.data)
            df_usuarios = pd.DataFrame(res_usuarios.data)
            df_palpites = pd.DataFrame(res_palpites.data) if res_palpites.data else pd.DataFrame(columns=["nome_amigo", "id_jogo", "palpite"])
            
            df_cross = df_usuarios.merge(df_jogos, how='cross')
            df_completo = df_cross.merge(df_palpites, left_on=['nome', 'id'], right_on=['nome_amigo', 'id_jogo'], how='left')
            
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
            
            # NOVIDADE: st.table resolve o scroll de vez!
            st.table(df_geral)

    # ------------------------------------------
    # 3. MEUS PALPITES 
    # ------------------------------------------
    elif menu == "Meus Palpites":
        st.subheader("Os Meus Palpites")
        rodada = st.number_input("Filtrar por Rodada", min_value=1, step=1, value=rodada_ativa_atual, key="rod_meus")
        
        jogos = supabase.table("jogos").select("*").eq("rodada", rodada).execute().data
        meus_palpites = supabase.table("palpites").select("*").eq("nome_amigo", st.session_state.nome_usuario).execute().data
        
        if jogos:
            agora = datetime.now(fuso_br)
            mapa_meus = {p['id_jogo']: p['palpite'] for p in meus_palpites}
            dados_view = []
            
            for jogo in jogos:
                partida = f"{jogo['time_casa']} x {jogo['time_fora']}"
                res_real = jogo.get("resultado_real") or "A aguardar..."
                
                fechamento = converter_para_br(jogo['horario_fechamento']) if jogo.get('horario_fechamento') else None
                jogo_fechado = fechamento and agora >= fechamento
                palpite_feito = mapa_meus.get(jogo['id'])
                
                if palpite_feito:
                    palpite_mostrar = palpite_feito
                else:
                    palpite_mostrar = "Empate (Auto)" if jogo_fechado else "Pendente (Ainda pode votar/editar)"
                        
                dados_view.append({
                    "Partida": partida,
                    "O Meu Palpite": palpite_mostrar,
                    "Resultado Real": res_real
                })
                
            df_view = pd.DataFrame(dados_view)
            # NOVIDADE: st.table e transformando Partida no index para ficar limpo
            st.table(df_view.set_index("Partida"))
        else:
            st.info("Nenhum jogo nesta rodada.")

    # ------------------------------------------
    # 4. CAMPEÃO DA RODADA
    # ------------------------------------------
    elif menu == "Campeão da Rodada":
        st.subheader("👑 Campeões por Rodada")
        
        res_jogos = supabase.table("jogos").select("id, rodada, resultado_real").not_.is_("resultado_real", "null").execute()
        res_usuarios = supabase.table("usuarios").select("nome").execute()
        res_palpites = supabase.table("palpites").select("nome_amigo, id_jogo, palpite").execute()
        
        if not res_jogos.data:
            st.info("Ainda não há jogos finalizados para determinar campeões.")
        else:
            df_jogos = pd.DataFrame(res_jogos.data)
            df_usuarios = pd.DataFrame(res_usuarios.data)
            df_palpites = pd.DataFrame(res_palpites.data) if res_palpites.data else pd.DataFrame(columns=["nome_amigo", "id_jogo", "palpite"])
            
            df_cross = df_usuarios.merge(df_jogos, how='cross')
            df_completo = df_cross.merge(df_palpites, left_on=['nome', 'id'], right_on=['nome_amigo', 'id_jogo'], how='left')
            
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
                    # NOVIDADE: Tabela desenrolada
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
        
        res_jogos_encerrados = supabase.table("jogos").select("id, rodada, resultado_real").not_.is_("resultado_real", "null").execute()
        res_usuarios = supabase.table("usuarios").select("nome").execute()
        res_palpites = supabase.table("palpites").select("nome_amigo, id_jogo, palpite").execute()
        
        if not res_jogos_encerrados.data:
            st.info("Ainda não há resultados finais lançados para contabilizar pontos.")
        else:
            df_jogos = pd.DataFrame(res_jogos_encerrados.data)
            df_usuarios = pd.DataFrame(res_usuarios.data)
            df_palpites = pd.DataFrame(res_palpites.data) if res_palpites.data else pd.DataFrame(columns=["nome_amigo", "id_jogo", "palpite"])
            
            df_cross = df_usuarios.merge(df_jogos, how='cross')
            df_completo = df_cross.merge(df_palpites, left_on=['nome', 'id'], right_on=['nome_amigo', 'id_jogo'], how='left')
            
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
            
            # NOVIDADE: Tabela desenrolada
            st.table(df_pivot)

    # ------------------------------------------
    # 6. VER PALPITES DA GALERA
    # ------------------------------------------
    elif menu == "Ver Palpites da Galera":
        st.subheader("Quem apostou no quê?")
        rodada = st.number_input("Rodada", min_value=1, step=1, value=rodada_ativa_atual)
        
        jogos = supabase.table("jogos").select("*").eq("rodada", rodada).execute().data
        palpites = supabase.table("palpites").select("*").execute().data
        usuarios = supabase.table("usuarios").select("nome").execute().data
        
        nomes_usuarios = [u['nome'] for u in usuarios]
        total_usuarios = len(nomes_usuarios)
        agora = datetime.now(fuso_br)
        
        if jogos:
            mapa_palpites = {(p['id_jogo'], p['nome_amigo']): p['palpite'] for p in palpites}
            dados_tabela = []
            
            for jogo in jogos:
                partida = f"{jogo['time_casa']} x {jogo['time_fora']}"
                fechamento = converter_para_br(jogo['horario_fechamento']) if jogo.get('horario_fechamento') else None
                passou_do_tempo = fechamento and agora >= fechamento
                
                votos_neste_jogo = sum(1 for nome in nomes_usuarios if (jogo['id'], nome) in mapa_palpites)
                todos_votaram = (votos_neste_jogo == total_usuarios)
                
                jogo_liberado = passou_do_tempo or todos_votaram
                
                for nome in nomes_usuarios:
                    palpite_real = mapa_palpites.get((jogo['id'], nome))
                    
                    if palpite_real:
                        palpite_visivel = palpite_real if jogo_liberado else "🔒 Oculto"
                    else:
                        palpite_visivel = "Empate (Auto)" if passou_do_tempo else "Pendente"
                        
                    dados_tabela.append({"Nome": nome, "Partida": partida, "Palpite": palpite_visivel})
                    
            df_completo = pd.DataFrame(dados_tabela)
            tabela = df_completo.pivot_table(index="Nome", columns="Partida", values="Palpite", aggfunc='first')
            
            st.table(tabela)
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
        
        res_pagamentos = supabase.table("pagamentos").select("*").execute().data
        if res_pagamentos:
            df_pag = pd.DataFrame(res_pagamentos)
            
            colunas_map = {
                "nome": "Participantes", "m02": "02/2026", "m03": "03/2026", "m04": "04/2026",
                "m05": "05/2026", "m06": "06/2026", "m07": "07/2026", "m08": "08/2026",
                "m09": "09/2026", "m10": "10/2026", "m11": "11/2026", "m12": "12/2026"
            }
            df_pag = df_pag.rename(columns=colunas_map)
            df_pag = df_pag.sort_values(by="Participantes").reset_index(drop=True)
            
            # Limpa o index (que era numérico) para focar apenas no Participante
            st.table(df_pag.set_index("Participantes"))
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
        2. **Maior quantidade de campeões da rodada**.

        **⏳ Limite de Palpites** * Os palpites podem ser inseridos ou alterados até **exatamente 30 minutos antes** do horário oficial de início da partida.  
        * Após esse limite, o jogo é bloqueado. Se não tiver deixado palpite, o sistema assumirá "Empate" automaticamente.  
        * Assim que o jogo bloqueia (ou assim que todos os participantes votarem), os palpites ficam públicos para todos verem.
        """)

    # ------------------------------------------
    # 10. ADMIN
    # ------------------------------------------
    elif menu == "⚙️ Admin":
        aba1, aba2, aba3, aba4 = st.tabs(["Partidas e Rodada", "Lançar Resultados", "📱 Relatórios WhatsApp", "💰 Gerir Pagamentos"])
        
        with aba1:
            st.subheader("1. Definir Rodada Ativa")
            nova_rodada_ativa = st.number_input("Qual a rodada atual do bolão?", min_value=1, step=1, value=rodada_ativa_atual)
            if st.button("Atualizar Rodada Ativa", use_container_width=True):
                supabase.table("configuracoes").upsert({"id": 1, "rodada_ativa": nova_rodada_ativa}).execute()
                st.success(f"Rodada ativa alterada para {nova_rodada_ativa}!")
                st.rerun()

            st.divider()

            st.subheader("2. Registar Novo Jogo")
            with st.form("novo_jogo"):
                col1, col2, col3 = st.columns(3)
                rod = col1.number_input("Rodada", min_value=1, step=1, value=rodada_ativa_atual)
                casa = col2.text_input("Visitada")
                fora = col3.text_input("Visitante")
                
                col4, col5 = st.columns(2)
                data_jogo = col4.date_input("Data do Jogo")
                hora_jogo = col5.time_input("Hora do Jogo", value=time(16, 0)) 
                
                if st.form_submit_button("Registar Partida", use_container_width=True):
                    dt_jogo = fuso_br.localize(datetime.combine(data_jogo, hora_jogo))
                    dt_fechamento = dt_jogo - timedelta(minutes=30)
                    
                    supabase.table("jogos").insert({
                        "rodada": rod, 
                        "time_casa": casa, 
                        "time_fora": fora,
                        "horario_fechamento": dt_fechamento.isoformat()
                    }).execute()
                    
                    st.success(f"Jogo registado! Limite de votação e edição: {dt_fechamento.strftime('%d/%m %H:%M')}")
        
        with aba2:
            st.subheader("Lançar / Editar Resultado Final")
            rod_resultado = st.number_input("Filtrar por Rodada", min_value=1, step=1, value=rodada_ativa_atual, key="rod_res")
            
            jogos_rodada = supabase.table("jogos").select("*").eq("rodada", rod_resultado).execute().data
            
            if jogos_rodada:
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
        
        with aba3:
            st.subheader("📱 Gerador de Relatórios WhatsApp")
            st.write(f"Estes relatórios baseiam-se na **Rodada {rodada_ativa_atual} (Ativa)**.")
            
            jogos_ativos = supabase.table("jogos").select("*").eq("rodada", rodada_ativa_atual).execute().data
            
            if not jogos_ativos:
                st.warning("Não há jogos registados na rodada ativa para gerar relatórios.")
            else:
                if st.button("📋 Gerar Relatório de Faltosos", use_container_width=True):
                    todos_usuarios = supabase.table("usuarios").select("nome").execute().data
                    nomes_todos = [u['nome'] for u in todos_usuarios]
                    
                    ids_jogos = [j['id'] for j in jogos_ativos]
                    palpites_feitos = supabase.table("palpites").select("nome_amigo").in_("id_jogo", ids_jogos).execute().data
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
                    msg = f"🏆 *Agenda da Rodada {rodada_ativa_atual}*\n\n"
                    for j in jogos_ativos:
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
            pagamentos = supabase.table("pagamentos").select("*").execute().data
            
            nomes_usuarios = [u['nome'] for u in usuarios]
            nomes_pagamentos = [p['nome'] for p in pagamentos]
            
            novos = [n for n in nomes_usuarios if n not in nomes_pagamentos]
            for novo in novos:
                supabase.table("pagamentos").insert({"nome": novo}).execute()
            
            pagamentos_atuais = supabase.table("pagamentos").select("*").execute().data
            if pagamentos_atuais:
                df_pagamentos = pd.DataFrame(pagamentos_atuais)
                df_pagamentos = df_pagamentos.sort_values(by="nome").reset_index(drop=True)
                
                # Fórmula para calcular a altura dinâmica baseada no número de participantes, evitando scroll no editor!
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