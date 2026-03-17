import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, time, timedelta
import pytz

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

# --- CONTROLO DE SESSÃO ---
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.nome_usuario = ""
    st.session_state.email_usuario = ""
    st.session_state.is_admin = False

# ==========================================
# ECRÃ DE ACESSO (LOGIN MELHORADO)
# ==========================================
if not st.session_state.logado:
    st.title("🔒 Acesso ao Bolão")
    st.write("Identifique-se para aceder aos palpites.")
    
    # Busca e-mail primeiro para saber qual formulário mostrar
    email_digitado = st.text_input("Qual o seu e-mail?")
    
    if email_digitado:
        email_limpo = email_digitado.lower().strip()
        resposta = supabase.table("usuarios").select("*").eq("email", email_limpo).execute()
        
        if len(resposta.data) > 0:
            usuario = resposta.data[0]
            
            # --- PRIMEIRO ACESSO (CRIAR SENHA) ---
            if not usuario.get("senha"):
                st.info(f"Olá, **{usuario['nome']}**! Este é o seu primeiro acesso. Crie uma palavra-passe para continuar.")
                with st.form("form_primeiro_acesso"):
                    nova_senha = st.text_input("Crie a sua palavra-passe:", type="password")
                    if st.form_submit_button("Guardar e Entrar"):
                        if nova_senha:
                            supabase.table("usuarios").update({"senha": nova_senha}).eq("email", email_limpo).execute()
                            st.success("Palavra-passe registada com sucesso!")
                            st.session_state.logado = True
                            st.session_state.nome_usuario = usuario['nome']
                            st.session_state.email_usuario = email_limpo
                            st.session_state.is_admin = usuario.get('is_admin', False)
                            st.rerun()
                        else:
                            st.warning("A palavra-passe não pode estar vazia.")
                            
            # --- ACESSO NORMAL (JÁ TEM SENHA) ---
            else:
                with st.form("form_login"):
                    senha_digitada = st.text_input("A sua palavra-passe:", type="password")
                    if st.form_submit_button("Entrar"):
                        if senha_digitada == usuario["senha"]:
                            st.session_state.logado = True
                            st.session_state.nome_usuario = usuario['nome']
                            st.session_state.email_usuario = email_limpo
                            st.session_state.is_admin = usuario.get('is_admin', False)
                            st.rerun()
                        else:
                            st.error("Palavra-passe incorreta!")
        else:
            st.error("E-mail não encontrado ou não autorizado! Fale com o administrador.")

# ==========================================
# SISTEMA PRINCIPAL
# ==========================================
else:
    col1, col2 = st.columns([8, 1])
    with col1:
        st.title("🏆 Bolão da Galera")
        st.write(f"Olá, **{st.session_state.nome_usuario}**!")
    with col2:
        if st.button("Sair", use_container_width=True):
            st.session_state.logado = False
            st.session_state.is_admin = False
            st.rerun()
            
    st.divider()

    opcoes_menu = ["Fazer Palpites", "Meus Palpites", "Ver Palpites da Galera", "Classificação"]
    if st.session_state.is_admin:
        opcoes_menu.append("⚙️ Admin")
        
    menu = st.sidebar.selectbox("Navegação", opcoes_menu)

    # ------------------------------------------
    # 1. FAZER PALPITES
    # ------------------------------------------
    if menu == "Fazer Palpites":
        st.subheader("Deixe os seus palpites")
        rodada_atual = st.number_input("Selecione a Rodada", min_value=1, step=1)
        
        jogos = supabase.table("jogos").select("*").eq("rodada", rodada_atual).execute().data
        
        if not jogos:
            st.info("Nenhum jogo registado para esta rodada ainda.")
        else:
            agora = datetime.now(fuso_br)
            ids_jogos_rodada = [j['id'] for j in jogos]
            palpites_existentes = supabase.table("palpites").select("id_jogo, palpite").eq("nome_amigo", st.session_state.nome_usuario).in_("id_jogo", ids_jogos_rodada).execute().data
            mapa_ja_palpitou = {p['id_jogo']: p['palpite'] for p in palpites_existentes}
            
            with st.form("form_palpites"):
                palpites_feitos = {}
                jogos_abertos = 0
                
                for jogo in jogos:
                    st.write(f"**{jogo['time_casa']} x {jogo['time_fora']}**")
                    
                    if jogo['id'] in mapa_ja_palpitou:
                        st.success(f"✅ Palpite bloqueado: **{mapa_ja_palpitou[jogo['id']]}**")
                    else:
                        if jogo.get('horario_fechamento'):
                            fechamento = converter_para_br(jogo['horario_fechamento'])
                            
                            if agora < fechamento:
                                st.caption(f"⏳ Fecha em: {fechamento.strftime('%d/%m às %H:%M')}")
                                opcoes = [jogo['time_casa'], "Empate", jogo['time_fora']]
                                escolha = st.radio("Vencedor:", opcoes, horizontal=True, index=1, key=f"jogo_{jogo['id']}")
                                palpites_feitos[jogo['id']] = escolha
                                jogos_abertos += 1
                            else:
                                st.error(f"🔒 Encerrado (Foi assumido 'Empate' automaticamente)")
                        else:
                            opcoes = [jogo['time_casa'], "Empate", jogo['time_fora']]
                            escolha = st.radio("Vencedor:", opcoes, horizontal=True, index=1, key=f"jogo_{jogo['id']}")
                            palpites_feitos[jogo['id']] = escolha
                            jogos_abertos += 1
                    
                    st.write("---")
                
                if jogos_abertos > 0:
                    enviar = st.form_submit_button("Guardar Novos Palpites")
                    if enviar:
                        for id_jogo, palpite in palpites_feitos.items():
                            # Usando upsert para garantir que não duplica
                            supabase.table("palpites").upsert({
                                "nome_amigo": st.session_state.nome_usuario,
                                "id_jogo": id_jogo,
                                "palpite": palpite
                            }).execute()
                        st.success("Palpites guardados com sucesso!")
                        st.rerun()
                else:
                    st.form_submit_button("Todos os jogos bloqueados ou já preenchidos", disabled=True)

    # ------------------------------------------
    # 2. MEUS PALPITES 
    # ------------------------------------------
    elif menu == "Meus Palpites":
        st.subheader("Os Meus Palpites")
        rodada = st.number_input("Filtrar por Rodada", min_value=1, step=1, key="rod_meus")
        
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
                    if jogo_fechado:
                        palpite_mostrar = "Empate (Auto)"
                    else:
                        palpite_mostrar = "Pendente (Ainda pode votar)"
                        
                dados_view.append({
                    "Partida": partida,
                    "O Meu Palpite": palpite_mostrar,
                    "Resultado Real": res_real
                })
                
            st.dataframe(pd.DataFrame(dados_view), hide_index=True, use_container_width=True)
        else:
            st.info("Nenhum jogo nesta rodada.")

    # ------------------------------------------
    # 3. VER PALPITES DA GALERA 
    # ------------------------------------------
    elif menu == "Ver Palpites da Galera":
        st.subheader("Quem apostou no quê?")
        rodada = st.number_input("Rodada", min_value=1, step=1)
        
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
                        
                    dados_tabela.append({
                        "Nome": nome,
                        "Partida": partida,
                        "Palpite": palpite_visivel
                    })
                    
            df_completo = pd.DataFrame(dados_tabela)
            tabela = df_completo.pivot_table(index="Nome", columns="Partida", values="Palpite", aggfunc='first')
            st.dataframe(tabela, use_container_width=True)
        else:
            st.info("Sem dados para exibir.")

    # ------------------------------------------
    # 4. CLASSIFICAÇÃO E TOTAL POR RODADA
    # ------------------------------------------
    elif menu == "Classificação":
        st.subheader("🏆 Classificação Geral e por Rodada")
        
        res_jogos_encerrados = supabase.table("jogos").select("id, rodada, resultado_real").not_.is_("resultado_real", "null").execute()
        res_usuarios = supabase.table("usuarios").select("nome").execute()
        res_palpites = supabase.table("palpites").select("nome_amigo, id_jogo, palpite").execute()
        
        if not res_jogos_encerrados.data:
            st.info("Ainda não há resultados finais lançados para contabilizar pontos.")
        else:
            df_jogos = pd.DataFrame(res_jogos_encerrados.data)
            df_usuarios = pd.DataFrame(res_usuarios.data)
            df_palpites = pd.DataFrame(res_palpites.data) if res_palpites.data else pd.DataFrame(columns=["nome_amigo", "id_jogo", "palpite"])
            
            # Cria a combinação de todos os usuários com todos os jogos finalizados (Cross Join)
            df_cross = df_usuarios.merge(df_jogos, how='cross')
            
            # Junta com os palpites reais
            df_completo = df_cross.merge(df_palpites, left_on=['nome', 'id'], right_on=['nome_amigo', 'id_jogo'], how='left')
            
            # REGRA MÁGICA: Se não houver palpite registado, preenche com 'Empate'
            df_completo['palpite'] = df_completo['palpite'].fillna('Empate')
            
            # Limpeza de texto para evitar erros de espaços ou maiúsculas/minúsculas
            df_completo['palpite_clean'] = df_completo['palpite'].astype(str).str.strip().str.lower()
            df_completo['resultado_clean'] = df_completo['resultado_real'].astype(str).str.strip().str.lower()
            
            # Calcula os Pontos
            df_completo['pontos'] = (df_completo['palpite_clean'] == df_completo['resultado_clean']).astype(int)
            
            # TABELA 1: Ranking Geral
            df_geral = df_completo.groupby('nome')['pontos'].sum().reset_index()
            df_geral = df_geral.sort_values(by='pontos', ascending=False).reset_index(drop=True)
            df_geral.index += 1
            df_geral.columns = ["Participante", "Total de Pontos"]
            
            col1, col2 = st.columns([1, 2])
            with col1:
                st.write("**Ranking Global**")
                st.dataframe(df_geral, use_container_width=True)
                
            # TABELA 2: Total por Rodada (Estilo Planilha)
            with col2:
                st.write("**Pontos por Rodada**")
                df_agrupado = df_completo.groupby(['nome', 'rodada'])['pontos'].sum().reset_index()
                
                # Cria a Tabela Dinâmica
                df_pivot = df_agrupado.pivot(index='nome', columns='rodada', values='pontos').fillna(0).astype(int)
                df_pivot.columns = [f"Rodada {col}" for col in df_pivot.columns]
                
                # Adiciona coluna de Total para organizar
                df_pivot['Total'] = df_pivot.sum(axis=1)
                df_pivot = df_pivot.sort_values(by='Total', ascending=False)
                
                # Mostra no site
                st.dataframe(df_pivot, use_container_width=True)

    # ------------------------------------------
    # 5. ADMIN
    # ------------------------------------------
    elif menu == "⚙️ Admin":
        st.subheader("1. Registar Novo Jogo")
        with st.form("novo_jogo"):
            col1, col2, col3 = st.columns([1, 2, 2])
            rod = col1.number_input("Rod", min_value=1, step=1)
            casa = col2.text_input("Equipa Visitada")
            fora = col3.text_input("Equipa Visitante")
            
            col4, col5 = st.columns(2)
            data_jogo = col4.date_input("Data do Jogo")
            hora_jogo = col5.time_input("Hora do Jogo", value=time(16, 0)) 
            
            if st.form_submit_button("Registar Partida"):
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
        
        st.subheader("2. Lançar Resultado Final")
        rod_resultado = st.number_input("Filtrar por Rodada", min_value=1, step=1, key="rod_res")
        jogos_pendentes = supabase.table("jogos").select("*").eq("rodada", rod_resultado).is_("resultado_real", "null").execute().data
        
        if jogos_pendentes:
            for jogo in jogos_pendentes:
                st.write(f"**{jogo['time_casa']} x {jogo['time_fora']}**")
                vencedor = st.selectbox("Quem ganhou?", [jogo['time_casa'], "Empate", jogo['time_fora']], key=f"res_{jogo['id']}")
                if st.button("Guardar Resultado", key=f"btn_{jogo['id']}"):
                    supabase.table("jogos").update({"resultado_real": vencedor}).eq("id", jogo["id"]).execute()
                    st.success("Resultado atualizado e classificação recalculada!")
                    st.rerun()
        else:
            st.write("Sem jogos a aguardar resultado nesta rodada.")