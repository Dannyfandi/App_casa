import streamlit as st
import pandas as pd
from datetime import datetime
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURATION ---
ROOMIES = ["Ale", "Ferb", "Fandi"]
CATS_PARENTS = ["Ale", "Fandi"]
SHEET_NAME = "RoomieData" # Make sure this matches your Sheet Name exactly

# --- GOOGLE SHEETS CONNECTION ---
def get_google_sheet_client():
    # We will load credentials from Streamlit Secrets (Step 4)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# --- DATA MANAGEMENT (CLOUD VERSION) ---
def load_data():
    try:
        client = get_google_sheet_client()
        sheet = client.open(SHEET_NAME).sheet1
        # We read the data from cell A1 where we store the big JSON
        data_raw = sheet.cell(1, 1).value
        
        if not data_raw:
            # If cell is empty, return default structure
            return {
                "tasks": [],
                "bills": [],
                "shopping": [],
                "furniture": []
            }
        return json.loads(data_raw)
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return {"tasks": [], "bills": [], "shopping": [], "furniture": []}

def save_data(data):
    try:
        client = get_google_sheet_client()
        sheet = client.open(SHEET_NAME).sheet1
        # Convert the whole data object to a string and save in Cell A1
        # This is a simple hack to keep your data structure without complex SQL
        json_str = json.dumps(data)
        sheet.update_cell(1, 1, json_str) 
    except Exception as e:
        st.error(f"Error saving data: {e}")

# Initialize Session State
if 'data' not in st.session_state:
    st.session_state.data = load_data()
if 'shopping_cart' not in st.session_state:
    st.session_state.shopping_cart = {} # {item_name: price}

# --- SIDEBAR & CONTEXT ---
st.sidebar.title("🏠 Menu")
mode = st.sidebar.radio("Sección", ["Resumen", "Responsabilidades", "Cuentas (Bills)", "Lista de Compras", "Muebles"])

# CATS MODE TOGGLE
st.sidebar.markdown("---")
is_cat_mode = st.sidebar.checkbox("🐱 Modo Gatos (Ale & Fandi)")

# Define current context (Names and Data ID)
current_users = CATS_PARENTS if is_cat_mode else ROOMIES
context_id = "cat" if is_cat_mode else "house"

# Helper to filter data by context
def get_context_data(key):
    return [x for x in st.session_state.data[key] if x.get('context') == context_id]

# --- LOGIC: DEBT CALCULATION ---
def calculate_debts(bills_list):
    # Matrix: Who owes Who how much
    balances = {u: 0 for u in current_users} 
    details = []
    
    for bill in bills_list:
        payer = bill['payer']
        debtors = bill['debtors']
        amount = bill['amount']
        
        if not debtors: continue
        
        split_amount = amount / len(debtors)
        
        # Payer "gains" the amount (because they paid)
        # But if payer is in debtors, they essentially pay themselves back that portion
        
        for d in debtors:
            if d != payer:
                # Debtor loses money (owes), Payer gains
                # We track net balance. + means you are owed money, - means you owe.
                balances[d] -= split_amount
                balances[payer] += split_amount

    return balances

# --- SECTIONS ---

# 1. RESUMEN (DASHBOARD)
if mode == "Resumen":
    st.title(f"{'🐱' if is_cat_mode else '🏠'} Resumen General")
    
    # Calculate Debts
    bills = get_context_data('bills')
    balances = calculate_debts(bills)
    
    st.subheader("Balances (Quién debe a quién)")
    
    # Logic to simplify debts
    for person, amount in balances.items():
        if amount > 1:
            st.success(f"{person} recupera: ${amount:,.0f}")
        elif amount < -1:
            st.error(f"{person} debe: ${abs(amount):,.0f}")
        else:
            st.info(f"{person} está a paz y salvo.")
            
    if st.button("Settle Up / Marcar Pagos"):
        st.info("Para marcar pagos, agrega una 'Cuenta' nueva donde el que debe paga al que le deben con categoría 'Pago Deuda'.")

# 2. RESPONSABILIDADES (TASKS)
elif mode == "Responsabilidades":
    st.title("📋 Responsabilidades")
    
    tab1, tab2 = st.tabs(["Mis Tareas", "Tablero General"])
    
    all_tasks = get_context_data('tasks')
    
    with tab2: # Create and View All
        st.subheader("Nueva Tarea")
        with st.form("new_task"):
            t_title = st.text_input("Tarea")
            t_assignees = st.multiselect("Asignado a", current_users, default=current_users)
            t_imp = st.slider("Importancia", 1, 3, 2)
            t_due = st.date_input("Fecha límite (Opcional)", value=None)
            if st.form_submit_button("Crear"):
                new_task = {
                    "id": str(datetime.now().timestamp()),
                    "title": t_title,
                    "assignees": t_assignees,
                    "status": "Pendiente",
                    "importance": t_imp,
                    "created": str(datetime.now().date()),
                    "due": str(t_due) if t_due else "Sin fecha",
                    "context": context_id
                }
                st.session_state.data['tasks'].append(new_task)
                save_data(st.session_state.data)
                st.rerun()

        st.markdown("---")
        st.subheader("Todas las tareas")
        for t in all_tasks:
            col1, col2, col3 = st.columns([3, 1, 1])
            col1.markdown(f"**{t['title']}** ({', '.join(t['assignees'])})")
            status_color = "🔴" if t['status'] == "Pendiente" else "🟡" if t['status'] == "En Progreso" else "🟢"
            col1.caption(f"Imp: {t['importance']} | Vence: {t['due']}")
            
            new_status = col2.selectbox("", ["Pendiente", "En Progreso", "Completado"], key=f"s_{t['id']}", index=["Pendiente", "En Progreso", "Completado"].index(t['status']), label_visibility="collapsed")
            
            if new_status != t['status']:
                t['status'] = new_status
                save_data(st.session_state.data)
                st.rerun()

    with tab1: # Personal
        me = st.selectbox("¿Quién eres hoy?", current_users)
        st.subheader(f"Tareas de {me}")
        my_tasks = [t for t in all_tasks if me in t['assignees'] and t['status'] != "Completado"]
        if not my_tasks:
            st.success("¡No tienes tareas pendientes!")
        for t in my_tasks:
            st.warning(f"{t['title']} ({t['status']}) - Imp: {t['importance']}")

# 3. CUENTAS (BILLS)
elif mode == "Cuentas (Bills)":
    st.title("💸 Historial de Gastos")
    
    with st.expander("➕ Agregar Gasto Manual"):
        with st.form("add_bill"):
            b_desc = st.text_input("Descripción")
            b_cat = st.selectbox("Categoría", ["Comida", "Servicios", "Hogar", "Salida", "Pago Deuda", "Muebles"])
            b_amount = st.number_input("Monto", min_value=0, step=100)
            b_payer = st.selectbox("Pagó", current_users)
            b_debtors = st.multiselect("Dividir entre", current_users, default=current_users)
            b_date = st.date_input("Fecha", value=datetime.now())
            
            if st.form_submit_button("Guardar Gasto"):
                new_bill = {
                    "date": str(b_date),
                    "amount": b_amount,
                    "category": b_cat,
                    "description": b_desc,
                    "payer": b_payer,
                    "debtors": b_debtors,
                    "context": context_id
                }
                st.session_state.data['bills'].append(new_bill)
                save_data(st.session_state.data)
                st.success("Guardado")
                st.rerun()
    
    # History
    bills = get_context_data('bills')
    if bills:
        df = pd.DataFrame(bills)
        st.dataframe(df[['date', 'description', 'amount', 'payer', 'category']], use_container_width=True)
    else:
        st.info("No hay gastos registrados aún.")

# 4. LISTA DE COMPRAS (SHOPPING)
elif mode == "Lista de Compras":
    st.title("🛒 Supermercado")
    
    # Separate Items into "To Buy" and "In Inventory"
    all_items = get_context_data('shopping')
    to_buy = [i for i in all_items if i['status'] == 'buy']
    have = [i for i in all_items if i['status'] == 'have']
    
    # MODE SELECTION
    shopping_mode = st.toggle("Modo: Ir de Compras (En el super)")
    
    if not shopping_mode:
        # --- PLANNING MODE ---
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📝 Falta Comprar")
            new_item = st.text_input("Agregar item (+ Enter)")
            if new_item:
                if not any(i['name'] == new_item for i in all_items):
                    st.session_state.data['shopping'].append({"name": new_item, "status": "buy", "context": context_id})
                    save_data(st.session_state.data)
                    st.rerun()
            
            for item in to_buy:
                if st.button(f"✅ Ya tenemos: {item['name']}", key=f"have_{item['name']}"):
                    item['status'] = 'have'
                    save_data(st.session_state.data)
                    st.rerun()
                if st.button(f"🗑️ Eliminar: {item['name']}", key=f"del_{item['name']}"):
                    st.session_state.data['shopping'].remove(item)
                    save_data(st.session_state.data)
                    st.rerun()

        with col2:
            st.subheader("🏠 En Casa")
            for item in have:
                if st.button(f"🔙 Se acabó: {item['name']}", key=f"buy_{item['name']}"):
                    item['status'] = 'buy'
                    save_data(st.session_state.data)
                    st.rerun()
    
    else:
        # --- SHOPPING CART MODE ---
        st.info("🛒 Estás comprando. Selecciona items para añadir al carrito y ponerles precio.")
        
        # 1. Select items from "To Buy" list to add to cart
        st.subheader("Lista de Pendientes")
        for item in to_buy:
            # If item is already in cart, show it differently
            in_cart = item['name'] in st.session_state.shopping_cart
            
            col_a, col_b = st.columns([3, 2])
            if in_cart:
                col_a.success(f"🛒 {item['name']}")
                price = col_b.number_input(f"Valor {item['name']}", value=st.session_state.shopping_cart[item['name']], key=f"price_{item['name']}")
                st.session_state.shopping_cart[item['name']] = price
                if col_b.button("Sacar", key=f"rem_{item['name']}"):
                    del st.session_state.shopping_cart[item['name']]
                    st.rerun()
            else:
                col_a.write(item['name'])
                if col_b.button("Al carro", key=f"add_{item['name']}"):
                    st.session_state.shopping_cart[item['name']] = 0 # Init price
                    st.rerun()

        # 2. Checkout
        st.markdown("---")
        st.subheader("Finalizar Compra")
        
        cart_total = sum(st.session_state.shopping_cart.values())
        cart_items = list(st.session_state.shopping_cart.keys())
        
        st.markdown(f"**Total Carrito: ${cart_total:,.0f}**")
        st.text(f"Items: {', '.join(cart_items)}")
        
        if cart_total > 0:
            with st.form("checkout"):
                c_payer = st.selectbox("¿Quién paga esto?", current_users)
                c_debtors = st.multiselect("¿Quiénes consumen esto?", current_users, default=current_users)
                
                if st.form_submit_button("Terminar Compra y Crear Cuenta"):
                    # 1. Create Bill Description
                    desc_str = ", ".join([f"{k} ({v})" for k,v in st.session_state.shopping_cart.items()])
                    
                    # 2. Add to Bills
                    new_bill = {
                        "date": str(datetime.now().date()),
                        "amount": cart_total,
                        "category": "Supermercado",
                        "description": desc_str,
                        "payer": c_payer,
                        "debtors": c_debtors,
                        "context": context_id
                    }
                    st.session_state.data['bills'].append(new_bill)
                    
                    # 3. Update Inventory (Mark bought items as 'have')
                    for item_name in cart_items:
                        # Find item in data
                        for db_item in st.session_state.data['shopping']:
                            if db_item['name'] == item_name and db_item['context'] == context_id:
                                db_item['status'] = 'have'
                    
                    # 4. Clear Cart and Save
                    st.session_state.shopping_cart = {}
                    save_data(st.session_state.data)
                    st.balloons()
                    st.success("Compra registrada y gastos divididos.")
                    st.rerun()

# 5. MUEBLES (FURNITURE)
elif mode == "Muebles":
    st.title("🛋️ Lista de Deseos / Muebles")
    
    # Form to add furniture
    with st.expander("Agregar Mueble Deseado"):
        with st.form("add_furn"):
            f_name = st.text_input("Artículo")
            f_est = st.number_input("Valor Estimado (Opcional)", step=1000)
            f_date = st.date_input("Fecha estimada compra", value=None)
            
            if st.form_submit_button("Agregar a lista"):
                new_f = {
                    "name": f_name,
                    "estimate": f_est,
                    "date": str(f_date) if f_date else "Sin fecha",
                    "status": "wish",
                    "context": context_id
                }
                st.session_state.data['furniture'].append(new_f)
                save_data(st.session_state.data)
                st.rerun()

    # List
    furn_list = get_context_data('furniture')
    wishes = [f for f in furn_list if f['status'] == 'wish']
    bought = [f for f in furn_list if f['status'] == 'bought']

    st.subheader("Por comprar")
    for item in wishes:
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"**{item['name']}** (~${item['estimate']})")
            c1.caption(f"Meta: {item['date']}")
            
            if c2.button("Comprar", key=f"buyf_{item['name']}"):
                # Convert to Bill Process
                st.session_state.temp_furn_buy = item
                # We handle the actual bill creation in a dialog or just inputs below
                # For simplicity, let's just use session state to show a form below
    
    # Handle Buying Flow for Furniture
    if 'temp_furn_buy' in st.session_state:
        item = st.session_state.temp_furn_buy
        st.info(f"Comprando: {item['name']}")
        with st.form("furn_checkout"):
            real_price = st.number_input("Precio Final", value=item['estimate'])
            p_payer = st.selectbox("Pagó", current_users)
            p_debtors = st.multiselect("Dividir entre", current_users, default=current_users)
            
            if st.form_submit_button("Confirmar Compra"):
                # Add Bill
                new_bill = {
                    "date": str(datetime.now().date()),
                    "amount": real_price,
                    "category": "Muebles",
                    "description": f"Compra Mueble: {item['name']}",
                    "payer": p_payer,
                    "debtors": p_debtors,
                    "context": context_id
                }
                st.session_state.data['bills'].append(new_bill)
                
                # Update Item Status
                # Find the actual object in the main list to update it
                for db_item in st.session_state.data['furniture']:
                     if db_item == item: # Compare objects
                         db_item['status'] = 'bought'
                
                del st.session_state.temp_furn_buy
                save_data(st.session_state.data)
                st.success("¡Mueble comprado!")
                st.rerun()

    if bought:
        with st.expander("Historial Comprados"):
            for item in bought:
                st.markdown(f"✅ {item['name']}")