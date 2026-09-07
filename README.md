<div align="center">

# 📚 Research Navigator

### *A modern academic discovery interface for exploring library resources beyond traditional catalogue search.*

Research Navigator is a web-based academic research discovery system designed for the **Central Library, Thapar Institute of Engineering & Technology (TIET)**.

![Python](https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![JavaScript](https://img.shields.io/badge/Frontend-JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black)
![HTML5](https://img.shields.io/badge/Markup-HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)
![Status](https://img.shields.io/badge/Status-Prototype-8A2BE2?style=for-the-badge)

**[Overview](#-overview)** · **[Problem Statement](#-problem-statement)** · **[Key Features](#-key-features)** · **[Design Philosophy](#-design-philosophy)** · **[Typography](#-typography)** · **[Architecture](#️-system-architecture)**

</div>

---

Instead of forcing users to navigate through a traditional catalogue using exact keywords, the system provides a more intuitive research experience through **concept exploration, topic-based discovery, relevance-ranked results, resource previews, and direct catalogue access**.

> ⚠️ **Prototype Data Status:** The current prototype uses a **6,398-record general book catalogue dataset** from `data/catalogue.json`. It is not yet populated with a dedicated academic-paper dataset. Concept discovery is currently based on **genre-oriented catalogue tags**, so some research-area searches may not produce meaningful concept matches until the production library dataset is integrated.

<br>

## ✨ Overview

Academic research often begins with an idea rather than a specific book, paper, or keyword.

Research Navigator is designed around that workflow.

Users can:

- 🔍 Search for research topics and concepts
- 🧭 Explore related research areas
- 🗂️ Discover resources through curated categories
- 📊 View relevance-ranked results
- 👀 Preview important resource information directly from result cards
- 📖 Open detailed resource information in a popup
- 🔗 Access the corresponding library catalogue record
- 💡 Explore resources without needing to know the exact catalogue terminology

The interface combines a **research-focused visual design** with a lightweight discovery workflow inspired by modern content platforms.

The research-area and concept-discovery experience is currently a **prototype layer** intended to demonstrate how the interface can work with a richer academic library dataset.

<div align="right"><a href="#-research-navigator">⬆ back to top</a></div>

---

## 🎯 Problem Statement

Traditional library catalogue systems are primarily designed around direct retrieval.

A user generally needs to know:

> **What exactly am I looking for?**

Research, however, often starts with:

> **I want to explore this area.**

This creates a gap between **research intent** and **catalogue search**.

Research Navigator attempts to bridge that gap by introducing a discovery layer on top of library resources.

Instead of treating the catalogue as the entire research experience, the system provides an interface for:

<div align="center">

### `Explore` → `Discover` → `Understand` → `Access`

</div>

<div align="right"><a href="#-research-navigator">⬆ back to top</a></div>

---

## 🚀 Key Features

<details open>
<summary><b>🔎 Research Search</b></summary>
<br>

Users can enter a research topic or concept and retrieve relevant resources through the backend search API.

The search interface is intentionally minimal so that the user can focus on the research question rather than the interface.

</details>

<details>
<summary><b>🧭 Research Area Discovery</b></summary>
<br>

The homepage provides topic-based discovery through research areas such as:

- AI & Machine Learning
- Computer Science
- Electronics
- Data & Analytics
- Sciences
- Management

Each research area contains smaller discovery cards that can directly launch a search.

> **Prototype note:** These research areas represent the intended discovery experience. The current catalogue data is based on general book genres rather than academic subject classifications, so these searches may not correspond directly to the current concept vocabulary.

</details>

<details>
<summary><b>📚 Library Highlights</b></summary>
<br>

The homepage also contains discovery-oriented sections for:

- Recently Added
- Trending Research
- Featured Collections
- Interdisciplinary Research

These sections provide an alternative to starting with a blank search box.

</details>

<details>
<summary><b>🗂️ Research Categories</b></summary>
<br>

Research topics can be explored through category-based navigation rather than requiring users to formulate a search query from scratch.

This creates a browsing experience closer to modern research/content discovery platforms.

</details>

<details>
<summary><b>📊 Relevance Information</b></summary>
<br>

Search results display a relevance score alongside the resource information.

This helps users quickly distinguish between highly relevant and less relevant results.

</details>

<details>
<summary><b>👀 Result Card Preview</b></summary>
<br>

Hovering over a result card reveals additional information without requiring the user to leave the search results page.

The preview can display information such as:

- Resource type
- Publication year
- Call number
- Identifier
- Availability/status

</details>

<details>
<summary><b>📖 Detailed Resource View</b></summary>
<br>

Clicking a result opens a detailed resource popup containing:

- Title
- Author
- Abstract
- Resource type
- Publication year
- Call number
- Identifier
- Subjects
- Relevance explanation
- Catalogue access
- Resource access, where available

This keeps the main search interface clean while still providing detailed information when required.

</details>

<details>
<summary><b>🔗 Catalogue Integration</b></summary>
<br>

Where a catalogue URL is available, the interface provides a direct:

**`CATALOGUE →`**

link to the corresponding library catalogue record.

Catalogue URLs are treated as optional, allowing the frontend to remain compatible with datasets where a catalogue link is not yet available.

</details>

<details>
<summary><b>💡 "Why Relevant?"</b></summary>
<br>

Each result can include an explanation describing why the resource was considered relevant to the user's query.

This provides additional context instead of presenting search results as a simple list of titles.

</details>

<details>
<summary><b>📱 Responsive Interface</b></summary>
<br>

The interface adapts to smaller screen sizes through responsive layouts for:

- Navigation
- Search
- Result cards
- Research categories
- Resource details
- Modal views

</details>

<div align="right"><a href="#-research-navigator">⬆ back to top</a></div>

---

## 🎨 Design Philosophy

Research Navigator intentionally avoids the appearance of a conventional catalogue interface.

The design uses a dark research-oriented visual system with:

| Element | Description |
|---|---|
| 🌑 Backgrounds | Deep neutral backgrounds |
| 🎛️ Surfaces | Muted surfaces |
| 🍷 Accents | Burgundy/magenta accents |
| ✨ Highlights | Subtle gold highlights |
| 🔠 Typography | High-contrast typography |
| 🔤 Metadata | Monospace metadata |

The visual language is influenced by academic libraries while borrowing interaction patterns from modern discovery platforms.

<div align="right"><a href="#-research-navigator">⬆ back to top</a></div>

---

## 🔤 Typography

The project uses three primary typefaces:

| Font | Purpose |
|---|---|
| **Manrope** | Headings, branding and major UI elements |
| **Inter** | General interface and body text |
| **IBM Plex Mono** | Technical metadata and labels |
| **Pixelify Sans** | Pixel-style hero text |

<div align="right"><a href="#-research-navigator">⬆ back to top</a></div>

---

## 🏗️ System Architecture

The project follows a frontend/backend architecture.

<details open>
<summary><b>View architecture diagram</b></summary>

```text
┌──────────────────────────────┐
│            User              │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│      Research Navigator      │
│          Frontend            │
│                              │
│  Search                      │
│  Research Areas              │
│  Result Cards                │
│  Hover Preview               │
│  Resource Modal              │
└──────────────┬───────────────┘
               │
               │ HTTP API
               ▼
┌──────────────────────────────┐
│           Backend            │
│        127.0.0.1:8000       │
│                              │
│  /api/health                 │
│  /api/search                 │
│  /api/concepts               │
│  /api/concept/{concept}      │
│  /api/resource/{id}          │
│  /api/resource/{id}/view     │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│      Library Resource Data   │
│                              │
│  Books                       │
│  Catalogue Records           │
│  Genre Tags                  │
│  Metadata                    │
└──────────────────────────────┘
