import streamlit as st
import pandas as pd
import base64
import json
import fitz  # PyMuPDF
from openai import OpenAI

# --- APP CONFIGURATION ---
st.set_page_config(page_title="Project Pricer Pro", page_icon="🪚", layout="wide")
st.markdown('<p>Impact-Site-Verification: 066f64be-0023-4366-9272-57570f76f543</p>', unsafe_allow_html=True)

st.title("🪚 The Project Pricer")
st.markdown("Upload a Plan. AI finds the **Master List**, compares prices, and estimates tax.")

# --- SECRET KEY LOGIC (THE FIX) ---
# This checks if you saved the key in the Cloud Secrets.
# If yes, it uses it automatically. If no, it asks the user.
if "OPENAI_API_KEY" in st.secrets:
    api_key = st.secrets["OPENAI_API_KEY"]
else:
    st.sidebar.header("🔑 Unlock AI")
    api_key = st.sidebar.text_input("Paste OpenAI API Key", type="password")

# --- SIDEBAR SETTINGS ---
st.sidebar.header("⚙️ Settings")
st.sidebar.divider()
zip_code = st.sidebar.text_input("Enter ZIP Code", max_chars=5, help="Used to estimate sales tax.")
tax_rate = st.sidebar.slider("Est. Tax Rate (%)", min_value=0.0, max_value=15.0, value=7.0, step=0.1)

def process_file(uploaded_file):
    image_data = []
    if uploaded_file.type == "application/pdf":
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        for page_num in range(min(len(doc), 5)): 
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
            img_bytes = pix.tobytes("png")
            base64_img = base64.b64encode(img_bytes).decode('utf-8')
            image_data.append(base64_img)
    else:
        base64_img = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
        image_data.append(base64_img)
    return image_data

uploaded_file = st.file_uploader("Upload Project", type=['png', 'jpg', 'jpeg', 'pdf'])

if uploaded_file and api_key:
    client = OpenAI(api_key=api_key)
    
    if st.button("🚀 Analyze Project"):
        with st.status("🤖 AI is auditing the plan...", expanded=True) as status:
            
            st.write("📄 Scanning pages for a 'Cut List' or 'Bill of Materials'...")
            images = process_file(uploaded_file)
            
            user_content = [{"type": "text", "text": "Analyze these project pages. Create a Master Shopping List."}]
            for img in images:
                user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}})

            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    response_format={"type": "json_object"}, 
                    messages=[
                        {
                            "role": "system",
                            "content": """
                            You are a master estimator analyzing a woodworking plan.
                            
                            YOUR GOAL: Create a MASTER aggregated list. 
                            
                            CRITICAL HIERARCHY RULES (FOLLOW THESE STRICTLY):
                            1. THE MASTER LIST IS GOD: If the document contains a "Cut List", "Bill of Materials", or "Parts List" table, EXTRACT COUNTS FROM THERE EXACTLY. 
                            2. IGNORE ASSEMBLY STEPS: Do NOT lower quantities based on instruction steps like "Attach the 2 legs". Only use assembly steps to find items MISSING from the master list.
                            3. VISUAL ESTIMATION: Only use visual estimation if NO text list exists.
                            4. HARDWARE: Price screws/glue by the BOX (Qty 1 = 1 Box).
                            5. VARIANCE: Estimate prices for Home Depot (HD) and Lowe's.
                            
                            Return JSON:
                            {
                                "shopping_list": [
                                    {"Item": "string", "Qty": number, "Reasoning": "string", "Price_HD": number, "Price_Lowes": number}
                                ],
                                "cut_list": [
                                    {"Part_Name": "string", "Dimension": "string", "Quantity": number, "Material_Source": "string"}
                                ]
                            }
                            """
                        },
                        {
                            "role": "user",
                            "content": user_content
                        }
                    ],
                    max_tokens=2500,
                )
                
                result_text = response.choices[0].message.content
                data = json.loads(result_text)
                status.update(label="Draft Complete!", state="complete", expanded=False)

                if 'data' not in st.session_state:
                    st.session_state['data'] = data

                tab1, tab2 = st.tabs(["📝 Shopping List & Tax", "🪚 Cut List"])
                
                with tab1:
                    if "shopping_list" in data:
                        df = pd.DataFrame(data["shopping_list"])
                        
                        st.info("👇 **Interactive Table:** Click any cell to fix the AI's counts or prices.")
                        
                        edited_df = st.data_editor(
                            df,
                            num_rows="dynamic",
                            use_container_width=True,
                            key="editor"
                        )
                        
                        # --- CALCULATION ENGINE ---
                        edited_df['Total HD'] = edited_df['Qty'] * edited_df['Price_HD']
                        edited_df['Total Lowes'] = edited_df['Qty'] * edited_df['Price_Lowes']
                        
                        hd_subtotal = edited_df['Total HD'].sum()
                        lowes_subtotal = edited_df['Total Lowes'].sum()
                        
                        tax_decimal = tax_rate / 100.0
                        hd_tax = hd_subtotal * tax_decimal
                        lowes_tax = lowes_subtotal * tax_decimal
                        
                        hd_final = hd_subtotal + hd_tax
                        lowes_final = lowes_subtotal + lowes_tax
                        
                        st.divider()
                        col1, col2 = st.columns(2)
                        
                        if hd_final < lowes_final:
                            with col1:
                                st.success(f"🏆 HOME DEPOT: ${hd_final:.2f}")
                                st.caption(f"Subtotal: ${hd_subtotal:.2f} | Tax: ${hd_tax:.2f}")
                            with col2:
                                st.error(f"Lowe's: ${lowes_final:.2f}")
                                st.caption(f"Subtotal: ${lowes_subtotal:.2f} | Tax: ${lowes_tax:.2f}")
                        else:
                            with col1:
                                st.error(f"Home Depot: ${hd_final:.2f}")
                                st.caption(f"Subtotal: ${hd_subtotal:.2f} | Tax: ${hd_tax:.2f}")
                            with col2:
                                st.success(f"🏆 LOWE'S: ${lowes_final:.2f}")
                                st.caption(f"Subtotal: ${lowes_subtotal:.2f} | Tax: ${lowes_tax:.2f}")
                                
                        st.warning("""
                        **⚠️ IMPORTANT DISCLAIMER:**
                        * **AI Estimation:** Always verify the Shopping List against your original plan before buying.
                        * **Pricing:** Prices are estimates based on national averages. 
                        """)

                with tab2:
                    if "cut_list" in data:
                        st.dataframe(pd.DataFrame(data["cut_list"]), use_container_width=True)

            except Exception as e:
                st.error(f"Error: {e}")

elif not api_key:
    st.warning("👈 Please paste your API Key to start.")