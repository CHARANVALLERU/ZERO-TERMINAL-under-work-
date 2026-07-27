# 🧠 ZERO Second Brain & Obsidian Vault Integration Guide

This guide provides step-by-step instructions for linking the **ZERO Second Brain** folder directly into the **Obsidian** desktop or mobile app, enabling real-time visual graph representation, automated daily log sync, and bidirectional memory integration with the **ZERO AI Engine**.

---

## 🏗️ Second Brain Vault Architecture

The vault is located at: `d:\ZERO(V1.0)\ZERO\obsidian_vault` (or `<PROJECT_ROOT>/obsidian_vault`).

```text
obsidian_vault/
├── .obsidian/                       # Native Obsidian configurations & plugins
│   ├── app.json                     # Live preview & [[Wikilink]] settings
│   ├── core-plugins.json            # Enabled plugins (Graph, Canvas, Backlinks)
│   └── templates.json               # Auto-template directory mapping
├── 00_Index_MOC.md                  # 🗺️ Master Map of Content (Graph Root)
├── 01_Daily_Logs/                   # 📅 Auto-synced daily pre-market predictions & voice logs
│   └── Index.md
├── 02_Mental_Models/                # 🧩 Cognitive decision-making frameworks
│   ├── First_Principles.md
│   ├── Probabilistic_Thinking.md
│   ├── Inversion.md
│   └── Index.md
├── 03_Cognitive_Biases/             # ⚠️ Risk mitigation & psychological bias logs
│   ├── FOMO.md
│   ├── Loss_Aversion.md
│   ├── Confirmation_Bias.md
│   ├── Human_Mentality_Framework.md
│   └── Index.md
├── 04_Quantitative_Strategies/      # ⚡ Execution parameters & market regimes
│   ├── Candlestick_Patterns_Encyclopedia.md
│   ├── Nautilus_Order_Types.md
│   ├── QuantDinger_Regimes.md
│   ├── Fincept_Multi_Agent_Consensus.md
│   └── Index.md
├── 05_AI_Memory/                    # 🤖 Executable AI system capabilities & skills
│   ├── AI_System_Capabilities_Executable_Skills.md
│   ├── Claude_Obsidian_Integration_Plan.md
│   ├── ZERO_Engine_Knowledge_Graph.md
│   └── Index.md
├── 06_System_Architecture/          # 🏛️ Technical ZERO Terminal specifications
│   ├── ZERO_v1.0_System_Overview.md
│   └── Index.md
└── Templates/                       # 📋 Standardized note creation templates
    └── daily_template.md
```

---

## 🛠️ Step-by-Step Procedure to Open in Obsidian

### Step 1: Download & Install Obsidian
If you don't already have Obsidian installed:
1. Download Obsidian for Windows / Mac / Linux / Mobile from [obsidian.md](https://obsidian.md/).
2. Run the installer and launch Obsidian.

### Step 2: Open `obsidian_vault` as a Vault
1. On the Obsidian splash window, click **"Open folder as vault"** (or click the Vault icon at the bottom-left of Obsidian -> **"Open existing folder"**).
2. Browse to your ZERO project directory:
   `d:\ZERO(V1.0)\ZERO\obsidian_vault`
3. Click **"Select Folder"**.

### Step 3: Verify Pre-Configured Settings
Because ZERO ships with a pre-built `.obsidian` directory, Obsidian will automatically configure:
- **Live Preview Mode**: Enabled by default.
- **[[Wikilinks]]**: Auto-resolution between notes.
- **Core Plugins**: Graph View, File Explorer, Search, Backlinks, Canvas, Outline, and Word Count are pre-activated.

### Step 4: Open the Graph View & Map of Content
1. In the file explorer on the left, click on `00_Index_MOC.md`.
2. Click the **Graph View** icon on the left ribbon (or press `Ctrl + G` / `Cmd + G`).
3. You will see a neural knowledge graph connecting mental models, cognitive bias alerts, quantitative strategies, and daily logs!

---

## 🔄 How Bidirectional Engine Sync Works

1. **Engine → Obsidian (Automated Daily Push)**:
   - When ZERO generates pre-market predictions, `engine/obsidian_sync.py` automatically updates today's daily log (`01_Daily_Logs/YYYY-MM-DD.md`) with predicted Open/High/Low/Close levels and confidence intervals.
   - Any voice notes or trade feedback logged in the UI automatically sync to this file.

2. **Obsidian → Engine (Dynamic AI Knowledge RAG)**:
   - When you open the **ZERO Brain Console** in Streamlit (`app.py`), `engine/zero_engine_kb.py` reads all notes inside `02_Mental_Models`, `03_Cognitive_Biases`, `04_Quantitative_Strategies`, `05_AI_Memory`, and `06_System_Architecture`.
   - The Gemini 3.1 Pro engine uses this knowledge as strict system context, warning you if your trade plan violates your personal rules or mental models.

---

## ✍️ Creating New Notes in Obsidian

To add a new Mental Model or Trading Rule:
1. Create a new markdown file inside `02_Mental_Models` or `03_Cognitive_Biases`.
2. Add standard `[[Wikilinks]]` pointing to other notes (e.g. `[[FOMO]]` or `[[First_Principles]]`).
3. Save the note—ZERO ENGINE will immediately absorb it into its AI reasoning memory on the next prompt refresh!
