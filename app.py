import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, time, timedelta
import pytz
import base64

# --- CONFIGURAÇÃO INICIAL E CONEXÃO ---
st.set_page_config(page_title="Bolão da Galera", page_icon="🏆", layout="wide")

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
    
    # NOVIDADE: E-mail e Senha juntos no mesmo formulário para ativar o "Salvar Senha" do navegador
    with st.form("form_login_unificado"):
        email_digitado = st.text_input("E-mail", autocomplete="username")
        senha_digitada = st.text_input("Palavra-passe", type="password", autocomplete="current-password")
        
        # Este botão serve tanto para entrar quanto para registrar a primeira senha
        submit = st.form_submit_button("Entrar", use_container_width=True)
        
        if submit:
            if email_digitado and senha_digitada:
                email_limpo = email_digitado.lower().strip()
                resposta = supabase.table("usuarios").select("*").eq("email", email_limpo).execute()
                
                if len(resposta.data) > 0:
                    usuario = resposta.data[0]
                    
                    # --- PRIMEIRO ACESSO (Cria a senha automaticamente) ---
                    if not usuario.get("senha"):
                        # Guarda a senha na base de dados
                        supabase.table("usuarios").update({"senha": senha_digitada}).eq("email", email_limpo).execute()
                        st.success("Primeiro acesso detetado! Palavra-passe registada.")
                        
                        # Salva a sessão e entra
                        st.query_params["sessao"] = codificar_sessao(email_limpo)
                        st.session_state.logado = True
                        st.session_state.nome_usuario = usuario['nome']
                        st.session_state.email_usuario = email_limpo
                        st.session_state.is_admin = usuario.get('is_admin', False)
                        st.rerun()
                        
                    # --- ACESSO NORMAL (Verifica a senha) ---
                    else:
                        if senha_digitada == usuario["senha"]:
                            # Salva a sessão na URL
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

    # Ordem dos menus
    opcoes_menu = [
        "Fazer Palpites", 
        "Classificação", 
        "Meus Palpites", 
        "Total por Rodada", 
        "Resultados da Rodada",
        "Ver Palpites da Galera"
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
    # 1. FAZER PALPITES
    # ------------------------------------------
    if menu == "Fazer Palpites":
        st.subheader(f"Deixe os seus palpites (Rodada {rodada_ativa_atual})")
        jogos = supabase.table("jogos").select("*").eq("rodada", rodada_ativa_atual).execute().data
        
        if not jogos:
            st.info(f"Nenhum jogo registado para a rodada {rodada_ativa_atual} ainda.")
        else:
            agora = datetime.now(fuso_br)
            ids_jogos_rodada = [j['id'] for j in jogos]
            palpites_existentes = supabase.table("palpites").select("id_jogo").eq("nome_amigo", st.session_state.nome_usuario).in_("id_jogo", ids_jogos_rodada).execute().data
            ids_ja_palpitados = [p['id_jogo'] for p in palpites_existentes]
            
            jogos_pendentes = []
            for jogo in jogos:
                if jogo['id'] in ids_ja_palpitados:
                    continue 
                
                if jogo.get('horario_fechamento'):
                    fechamento = converter_para_br(jogo['horario_fechamento'])
                    if agora >= fechamento:
                        continue 
                
                jogos_pendentes.append(jogo)

            if not jogos_pendentes:
                st.success("🎉 Você não tem palpites pendentes para esta rodada! (Todos os jogos foram votados ou já fecharam).")
            else:
                with st.form("form_palpites"):
                    palpites_feitos = {}
                    
                    for jogo in jogos_pendentes:
                        st.write(f"⚽ **{jogo['time_casa']} x {jogo['time_fora']}**")
                        
                        opcoes = [jogo['time_casa'], "Empate", jogo['time_fora']]
                        fechamento = converter_para_br(jogo['horario_fechamento']) if jogo.get('horario_fechamento') else None
                        
                        if fechamento:
                            st.caption(f"⏳ Fecha em: {fechamento.strftime('%d/%m às %H:%M')}")
                            
                        escolha = st.selectbox("Vencedor:", opcoes, index=1, key=f"jogo_{jogo['id']}")
                        palpites_feitos[jogo['id']] = escolha
                        
                        st.write("---")
                    
                    enviar = st.form_submit_button("Guardar Novos Palpites", use_container_width=True)
                    if enviar:
                        for id_jogo, palpite in palpites_feitos.items():
                            supabase.table("palpites").upsert({
                                "nome_amigo": st.session_state.nome_usuario,
                                "id_jogo": id_jogo,
                                "palpite": palpite
                            }).execute()
                        st.success("Palpites guardados com sucesso!")
                        st.rerun()

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
            
            df_geral = df_completo.groupby('nome')['pontos'].sum().reset_index()
            df_geral = df_geral.sort_values(by=['pontos', 'nome'], ascending=[False, True]).reset_index(drop=True)
            df_geral.index += 1
            df_geral.columns = ["Participante", "Total de Pontos"]
            
            st.dataframe(df_geral, use_container_width=True, height=450)

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
                    palpite_mostrar = "Empate (Auto)" if jogo_fechado else "Pendente (Ainda pode votar)"
                        
                dados_view.append({
                    "Partida": partida,
                    "O Meu Palpite": palpite_mostrar,
                    "Resultado Real": res_real
                })
                
            st.dataframe(pd.DataFrame(dados_view), hide_index=True, use_container_width=True)
        else:
            st.info("Nenhum jogo nesta rodada.")

    # ------------------------------------------
    # 4. TOTAL POR RODADA
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
            df_pivot = df_agrupado.pivot(index='nome', columns='rodada', values='pontos').fillna(0).astype(int)
            df_pivot.columns = [f"Rodada {col}" for col in df_pivot.columns]
            
            df_pivot['Total'] = df_pivot.sum(axis=1)
            df_pivot = df_pivot.sort_values(by=['Total', 'nome'], ascending=[False, True])
            
            st.dataframe(df_pivot, use_container_width=True, height=450)

    # ------------------------------------------
    # 5. RESULTADOS DA RODADA
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
                
            st.dataframe(pd.DataFrame(dados_view), hide_index=True, use_container_width=True)
        else:
            st.info("Nenhum jogo registado para esta rodada.")

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
        agora = datetime.now(fuso_br)
        
        if jogos:
            mapa_palpites = {(p['id_jogo'], p['nome_amigo']): p['palpite'] for p in palpites}
            dados_tabela = []
            
            for jogo in jogos:
                partida = f"{jogo['time_casa']} x {jogo['time_fora']}"
                fechamento = converter_para_br(jogo['horario_fechamento']) if jogo.get('horario_fechamento') else None
                jogo_fechado = fechamento and agora >= fechamento
                
                for nome in nomes_usuarios:
                    palpite_real = mapa_palpites.get((jogo['id'], nome))
                    
                    if palpite_real:
                        palpite_visivel = palpite_real if jogo_fechado else "🔒 Oculto"
                    else:
                        palpite_visivel = "Empate (Auto)" if jogo_fechado else "Pendente"
                        
                    dados_tabela.append({"Nome": nome, "Partida": partida, "Palpite": palpite_visivel})
                    
            df_completo = pd.DataFrame(dados_tabela)
            tabela = df_completo.pivot_table(index="Nome", columns="Partida", values="Palpite", aggfunc='first')
            st.dataframe(tabela, use_container_width=True)
        else:
            st.info("Sem dados para exibir.")

    # ------------------------------------------
    # 7. ADMIN
    # ------------------------------------------
    elif menu == "⚙️ Admin":
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
                dt_fechamento = dt_jogo - timedelta(hours=1, minutes=59)
                
                supabase.table("jogos").insert({
                    "rodada": rod, 
                    "time_casa": casa, 
                    "time_fora": fora,
                    "horario_fechamento": dt_fechamento.isoformat()
                }).execute()
                
                st.success(f"Jogo registado! Limite de votação: {dt_fechamento.strftime('%d/%m %H:%M')}")
        
        st.divider()
        
        st.subheader("3. Lançar Resultado Final")
        rod_resultado = st.number_input("Filtrar por Rodada", min_value=1, step=1, value=rodada_ativa_atual, key="rod_res")
        jogos_pendentes = supabase.table("jogos").select("*").eq("rodada", rod_resultado).is_("resultado_real", "null").execute().data
        
        if jogos_pendentes:
            for jogo in jogos_pendentes:
                st.write(f"**{jogo['time_casa']} x {jogo['time_fora']}**")
                vencedor = st.selectbox("Quem ganhou?", [jogo['time_casa'], "Empate", jogo['time_fora']], key=f"res_{jogo['id']}")
                if st.button("Guardar Resultado", key=f"btn_{jogo['id']}", use_container_width=True):
                    supabase.table("jogos").update({"resultado_real": vencedor}).eq("id", jogo["id"]).execute()
                    st.success("Resultado atualizado e classificação recalculada!")
                    st.rerun()
                st.write("---")
        else:
            st.write("Sem jogos a aguardar resultado nesta rodada.")