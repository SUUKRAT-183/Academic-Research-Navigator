# Research Navigator

> A modern academic discovery interface for exploring library resources beyond traditional catalogue search.

Research Navigator is a web-based academic research discovery system designed for the **Central Library, Thapar Institute of Engineering & Technology (TIET)**.

Instead of forcing users to navigate through a traditional catalogue using exact keywords, the system provides a more intuitive research experience through **concept exploration, topic-based discovery, relevance-ranked results, resource previews, and direct catalogue access**.

---

## ✨ Overview

Academic research often begins with an idea rather than a specific book, paper, or keyword.

Research Navigator is designed around that workflow.

Users can:

- Search for research topics and concepts
- Explore related research areas
- Discover resources through curated categories
- View relevance-ranked results
- Preview important resource information directly from result cards
- Open detailed resource information in a popup
- Access the corresponding library catalogue record
- Explore resources without needing to know the exact catalogue terminology

The interface combines a **research-focused visual design** with a lightweight discovery workflow inspired by modern content platforms.

---

## 🎯 Problem Statement

Traditional library catalogue systems are primarily designed around direct retrieval.

A user generally needs to know:

> What exactly am I looking for?

Research, however, often starts with:

> I want to explore this area.

This creates a gap between **research intent** and **catalogue search**.

Research Navigator attempts to bridge that gap by introducing a discovery layer on top of library resources.

Instead of treating the catalogue as the entire research experience, the system provides an interface for:

**Explore → Discover → Understand → Access**

---

## 🚀 Key Features

### 🔎 Research Search

Users can enter a research topic or concept and retrieve relevant resources through the backend search API.

The search interface is intentionally minimal so that the user can focus on the research question rather than the interface.

---

### 🧭 Research Area Discovery

The homepage provides topic-based discovery through research areas such as:

- AI & Machine Learning
- Computer Science
- Electronics
- Data & Analytics
- Sciences
- Management

Each research area contains smaller discovery cards that can directly launch a search.

---

### 📚 Library Highlights

The homepage also contains discovery-oriented sections for:

- Recently Added
- Trending Research
- Featured Collections
- Interdisciplinary Research

These sections provide an alternative to starting with a blank search box.

---

### 🗂️ Research Categories

Research topics can be explored through category-based navigation rather than requiring users to formulate a search query from scratch.

This creates a browsing experience closer to modern research/content discovery platforms.

---

### 📊 Relevance Information

Search results display a relevance score alongside the resource information.

This helps users quickly distinguish between highly relevant and less relevant results.

---

### 👀 Result Card Preview

Hovering over a result card reveals additional information without requiring the user to leave the search results page.

The preview can display information such as:

- Resource type
- Publication year
- Call number
- Identifier
- Availability/status

---

### 📖 Detailed Resource View

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

---

### 🔗 Catalogue Integration

Where a catalogue URL is available, the interface provides a direct:

**CATALOGUE →**

link to the corresponding library catalogue record.

Catalogue URLs are treated as optional, allowing the frontend to remain compatible with datasets where a catalogue link is not yet available.

---

### 💡 "Why Relevant?"

Each result can include an explanation describing why the resource was considered relevant to the user's query.

This provides additional context instead of presenting search results as a simple list of titles.

---

### 📱 Responsive Interface

The interface adapts to smaller screen sizes through responsive layouts for:

- Navigation
- Search
- Result cards
- Research categories
- Resource details
- Modal views

---

## 🎨 Design Philosophy

Research Navigator intentionally avoids the appearance of a conventional catalogue interface.

The design uses a dark research-oriented visual system with:

- Deep neutral backgrounds
- Muted surfaces
- Burgundy/magenta accents
- Subtle gold highlights
- High-contrast typography
- Monospace metadata

The visual language is influenced by academic libraries while borrowing interaction patterns from modern discovery platforms.

---

## 🔤 Typography

The project uses three primary typefaces:

| Font | Purpose |
|---|---|
| Manrope | Headings, branding and major UI elements |
| Inter | General interface and body text |
| IBM Plex Mono | Technical metadata and labels |
| Pixelify Sans | Pixel-style hero text |

---

## 🏗️ System Architecture

The project follows a frontend/backend architecture.

```text
┌──────────────────────────────┐
│          User                │
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
│          Backend             │
│       127.0.0.1:8000        │
│                              │
│  /api/search                 │
│  /api/concept/{concept}      │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│     Academic Resource Data   │
│                              │
│  Books                       │
│  Papers                      │
│  Library Resources           │
│  Metadata                    │
└──────────────────────────────┘
