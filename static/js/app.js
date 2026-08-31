// State Management
let user = null;
let token = null;
let conversations = [];
let libraryDocuments = []; // Store library documents globally
let activeConversationId = null;
let attachedFile = null; // { id, name, size }
let selectedLanguage = "English";
let selectedDocumentType = "Legal Agreement"; // Active document type mode
let compareMode = false; // Comparison workspace active flag
let selectedCompareDocs = []; // List of document IDs selected for comparison
let searchGrounding = false;
let mediaRecorder = null; // for voice input fallback
let recognition = null; // SpeechRecognition instance
let loadedQuickSummaryForDoc = null;

// API Configuration
const BASE_URL = window.location.origin;

// Global fetch interceptor to handle token expiration / 401 Unauthorized errors
const originalFetch = window.fetch;
window.fetch = async function (...args) {
    const response = await originalFetch(...args);
    if (response.status === 401) {
        const url = typeof args[0] === 'string' ? args[0] : args[0].url;
        // Avoid intercepting auth calls themselves to prevent infinite recursion
        if (url && !url.includes('/api/auth/login') && !url.includes('/api/auth/signup') && !url.includes('/api/auth/logout')) {
            console.warn("Unauthorized API call detected (401). Logging out...");
            handleLogout();
        }
    }
    return response;
};

// DOM Elements
const authOverlay = document.getElementById("auth-overlay");
const loginForm = document.getElementById("login-form");
const signupForm = document.getElementById("signup-form");
const switchSignup = document.getElementById("switch-to-signup");
const switchLogin = document.getElementById("switch-to-login");
const authError = document.getElementById("auth-error");

const sidebar = document.getElementById("sidebar");
const collapseSidebarBtn = document.getElementById("collapse-sidebar-btn");
const mobileToggleBtn = document.getElementById("mobile-toggle-btn");
const newChatBtn = document.getElementById("new-chat-btn");
const docSearchInput = document.getElementById("doc-search-input");
const recentChatsList = document.getElementById("recent-chats-list");
const documentsLibraryList = document.getElementById("documents-library-list");

const activeChatTitle = document.getElementById("active-chat-title");
const currentLangIndicator = document.getElementById("current-lang-indicator");
const messagesContainer = document.getElementById("messages-container");
const zeroState = document.getElementById("zero-state");

const chatComposerForm = document.getElementById("chat-composer-form");
const chatInput = document.getElementById("chat-input");
const fileUploader = document.getElementById("file-uploader");
const attachBtn = document.getElementById("attach-btn");
const voiceBtn = document.getElementById("voice-btn");
const webSearchToggle = document.getElementById("web-search-toggle");
const sendBtn = document.getElementById("send-btn");
const attachedFilePreview = document.getElementById("attached-file-preview");
const filePillName = document.getElementById("file-pill-name");
const filePillSize = document.getElementById("file-pill-size");
const fileUploadProgress = document.getElementById("file-upload-progress");
const removeAttachmentBtn = document.getElementById("remove-attachment-btn");

const mismatchModal = document.getElementById("mismatch-modal");
const mismatchMessageText = document.getElementById("mismatch-message-text");
const mismatchBtnForce = document.getElementById("mismatch-btn-force");
const mismatchBtnChange = document.getElementById("mismatch-btn-change");
const mismatchBtnCancel = document.getElementById("mismatch-btn-cancel");

// Modals
const settingsModal = document.getElementById("settings-modal");
const profileModal = document.getElementById("profile-modal");
const settingsTriggerBtn = document.getElementById("settings-trigger-btn");
const profileTriggerBtn = document.getElementById("profile-trigger-btn");
const logoutBtn = document.getElementById("logout-btn");
const languageSelect = document.getElementById("language-select");
const profileFullNameDisplay = document.getElementById("profile-fullname-display");
const profileEmailDisplay = document.getElementById("profile-email-display");

// ==========================================================================
// INITIALIZATION & SESSION MANAGEMENT
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
    // 1. Check local session
    token = localStorage.getItem("legalens_jwt_token");
    if (token) {
        checkSession();
    } else {
        showAuth(true);
    }

    // 2. Setup Event Listeners
    setupEventListeners();
    setupSpeechRecognition();
});

function showAuth(show) {
    if (show) {
        authOverlay.classList.remove("hidden");
        document.getElementById("app").classList.remove("auth-hidden");
    } else {
        authOverlay.classList.add("hidden");
        document.getElementById("app").classList.add("auth-hidden");
    }
}

async function checkSession() {
    try {
        const response = await fetch(`${BASE_URL}/api/auth/me`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (response.ok) {
            user = await response.json();
            showAuth(false);
            initWorkspace();
        } else {
            localStorage.removeItem("legalens_jwt_token");
            showAuth(true);
        }
    } catch (err) {
        console.error("Session verification failed:", err);
        showAuth(true);
    }
}

// ==========================================================================
// EVENT LISTENERS & UI INTERACTIONS
// ==========================================================================

function setupEventListeners() {
    // Auth Switch
    switchSignup.addEventListener("click", () => {
        loginForm.classList.add("hidden");
        signupForm.classList.remove("hidden");
        authError.classList.add("hidden");
    });
    switchLogin.addEventListener("click", () => {
        signupForm.classList.add("hidden");
        loginForm.classList.remove("hidden");
        authError.classList.add("hidden");
    });

    // Form Submissions
    loginForm.addEventListener("submit", handleLogin);
    signupForm.addEventListener("submit", handleSignup);
    chatComposerForm.addEventListener("submit", handleMessageSubmit);

    // Sidebar Toggles
    collapseSidebarBtn.addEventListener("click", () => {
        document.getElementById("app").classList.toggle("sidebar-collapsed");
    });
    mobileToggleBtn.addEventListener("click", () => {
        document.getElementById("app").classList.toggle("sidebar-open");
    });

    // Sidebar Actions
    newChatBtn.addEventListener("click", () => {
        exitCompareMode();
        handleNewChat();
    });
    docSearchInput.addEventListener("input", handleDocumentSearch);

    // Compare Documents Mode Triggers
    const compareModeBtn = document.getElementById("compare-mode-btn");
    compareModeBtn.addEventListener("click", toggleCompareMode);

    const closeComparisonBtn = document.getElementById("close-comparison-btn");
    closeComparisonBtn.addEventListener("click", exitCompareMode);

    const executeComparisonBtn = document.getElementById("execute-comparison-btn");
    executeComparisonBtn.addEventListener("click", runComparison);

    // Header Language Selector Sync
    const headerLanguageSelect = document.getElementById("header-language-select");
    headerLanguageSelect.addEventListener("change", (e) => {
        selectedLanguage = e.target.value;
        languageSelect.value = selectedLanguage;
    });

    // Modal Settings Language Sync
    languageSelect.addEventListener("change", (e) => {
        selectedLanguage = e.target.value;
        headerLanguageSelect.value = selectedLanguage;
    });

    // Document Type Tabs Listeners (Feature 1 & 12)
    const docTypeTabs = document.querySelectorAll(".doc-type-tab");
    docTypeTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            const docType = tab.dataset.type;
            selectDocumentType(docType);
        });
    });

    // Info Side Panel Trigger Listeners (Feature 10)
    const infoPanelTrigger = document.getElementById("info-panel-trigger");
    const infoSidePanel = document.getElementById("info-side-panel");
    infoPanelTrigger.addEventListener("click", () => {
        infoSidePanel.classList.toggle("collapsed");
    });

    const closeInfoPanelBtn = document.getElementById("close-info-panel-btn");
    closeInfoPanelBtn.addEventListener("click", () => {
        infoSidePanel.classList.add("collapsed");
    });

    // Textarea Auto-growth & Send keybinding
    chatInput.addEventListener("input", () => {
        chatInput.style.height = "auto";
        chatInput.style.height = (chatInput.scrollHeight - 10) + "px";
        
        if (chatInput.value.trim().length > 0) {
            sendBtn.classList.add("active");
        } else {
            sendBtn.classList.remove("active");
        }
    });

    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            chatComposerForm.requestSubmit();
        }
    });

    // File attachments click redirect
    attachBtn.addEventListener("click", () => fileUploader.click());
    fileUploader.addEventListener("change", handleFileUpload);
    removeAttachmentBtn.addEventListener("click", removeAttachedFile);

    // Document Dashboard Quick Actions
    const btnExplainFull = document.getElementById("btn-explain-full");
    if (btnExplainFull) btnExplainFull.addEventListener("click", handleExplainFullDocument);

    const btnWhatToKnow = document.getElementById("btn-what-to-know");
    if (btnWhatToKnow) btnWhatToKnow.addEventListener("click", handleWhatShouldIKnow);

    const btnQuickRisks = document.getElementById("btn-quick-risks");
    if (btnQuickRisks) btnQuickRisks.addEventListener("click", handleQuickRisks);

    const btnNextActions = document.getElementById("btn-next-actions");
    if (btnNextActions) btnNextActions.addEventListener("click", handleNextActions);

    // Mismatch resolution buttons
    mismatchBtnForce.addEventListener("click", () => {
        if (attachedFile && attachedFile.id) {
            handleMismatchResolution(attachedFile.id, 'force');
        }
    });
    mismatchBtnChange.addEventListener("click", () => {
        if (attachedFile && attachedFile.id && attachedFile.detectedType) {
            handleMismatchResolution(attachedFile.id, 'change', attachedFile.detectedType);
        }
    });
    mismatchBtnCancel.addEventListener("click", () => {
        if (attachedFile && attachedFile.id) {
            handleMismatchResolution(attachedFile.id, 'cancel');
        }
    });

    // Settings Toggle / Controls
    settingsTriggerBtn.addEventListener("click", () => toggleModal("settings-modal", true));
    profileTriggerBtn.addEventListener("click", () => {
        if (user) {
            profileFullNameDisplay.innerText = user.full_name || "User Profile";
            profileEmailDisplay.innerText = user.email;
        }
        toggleModal("profile-modal", true);
    });
    logoutBtn.addEventListener("click", handleLogout);

    // Web Search ground toggle
    webSearchToggle.addEventListener("click", () => {
        searchGrounding = !searchGrounding;
        if (searchGrounding) {
            webSearchToggle.classList.remove("toggle-off");
            webSearchToggle.classList.add("toggle-on");
        } else {
            webSearchToggle.classList.remove("toggle-on");
            webSearchToggle.classList.add("toggle-off");
        }
    });
}

function toggleModal(modalId, show) {
    const modal = document.getElementById(modalId);
    if (show) {
        modal.classList.remove("hidden");
    } else {
        modal.classList.add("hidden");
    }
}

function saveSettings() {
    selectedLanguage = languageSelect.value;
    currentLangIndicator.querySelector("span").innerText = selectedLanguage;
    toggleModal("settings-modal", false);
}

// ==========================================================================
// AUTHENTICATION OPERATIONS
// ==========================================================================

async function handleLogin(e) {
    e.preventDefault();
    const email = document.getElementById("login-email").value;
    const password = document.getElementById("login-password").value;
    
    try {
        const response = await fetch(`${BASE_URL}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });
        
        const data = await response.json();
        if (response.ok) {
            token = data.access_token;
            localStorage.setItem("legalens_jwt_token", token);
            user = data.user;
            showAuth(false);
            initWorkspace();
        } else {
            showAuthError(data.detail || "Authentication failed.");
        }
    } catch (err) {
        showAuthError("Server is unreachable. Please verify configuration.");
    }
}

async function handleSignup(e) {
    e.preventDefault();
    const full_name = document.getElementById("signup-name").value;
    const email = document.getElementById("signup-email").value;
    const password = document.getElementById("signup-password").value;
    
    try {
        const response = await fetch(`${BASE_URL}/api/auth/signup`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password, full_name })
        });
        
        const data = await response.json();
        if (response.ok) {
            // Some supabase configurations require email validation.
            // If session is returned, login directly
            if (data.access_token) {
                token = data.access_token;
                localStorage.setItem("legalens_jwt_token", token);
                user = data.user;
                showAuth(false);
                initWorkspace();
            } else {
                showAuthError("Account created! Please sign in.");
                signupForm.classList.add("hidden");
                loginForm.classList.remove("hidden");
            }
        } else {
            showAuthError(data.detail || "Signup failed.");
        }
    } catch (err) {
        showAuthError("Server is unreachable.");
    }
}

function showAuthError(msg) {
    authError.innerText = msg;
    authError.classList.remove("hidden");
}

async function handleLogout() {
    try {
        await fetch(`${BASE_URL}/api/auth/logout`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` }
        });
    } catch (err) {
        console.error("Logout api error:", err);
    }
    localStorage.removeItem("legalens_jwt_token");
    user = null;
    token = null;
    showAuth(true);
}

// ==========================================================================
// WORKSPACE ACTIONS & LOADERS
// ==========================================================================

async function initWorkspace() {
    // 1. Fetch conversations list
    await fetchConversations();
    // 2. Fetch document library list
    await fetchDocumentLibrary();
    // 3. Load active conversation or start a new one automatically
    if (conversations.length > 0) {
        loadConversation(conversations[0].id, conversations[0].title);
    } else {
        handleNewChat();
    }
}

async function fetchConversations() {
    try {
        const response = await fetch(`${BASE_URL}/api/conversations`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (response.ok) {
            conversations = await response.json();
            renderConversationsList();
        }
    } catch (err) {
        console.error("Error fetching chats:", err);
    }
}

function renderConversationsList() {
    recentChatsList.innerHTML = "";
    if (conversations.length === 0) {
        recentChatsList.innerHTML = `<div class="list-placeholder">No recent chats</div>`;
        return;
    }
    
    conversations.forEach(c => {
        const li = document.createElement("li");
        li.className = `sidebar-list-item ${c.id === activeConversationId ? 'active' : ''}`;
        li.dataset.id = c.id;
        
        li.innerHTML = `
            <i class="fa-regular fa-comment"></i>
            <span class="list-item-title">${escapeHTML(c.title)}</span>
            <div class="list-item-actions">
                <button class="item-action-btn btn-delete" onclick="event.stopPropagation(); deleteChat('${c.id}')" title="Delete Chat">
                    <i class="fa-regular fa-trash-can"></i>
                </button>
            </div>
        `;
        
        li.addEventListener("click", () => loadConversation(c.id, c.title));
        recentChatsList.appendChild(li);
    });
}

async function loadConversation(id, title) {
    activeConversationId = id;
    activeChatTitle.innerText = title;
    
    // Highlight sidebar
    document.querySelectorAll("#recent-chats-list .sidebar-list-item").forEach(item => {
        if (item.dataset.id === id) {
            item.classList.add("active");
        } else {
            item.classList.remove("active");
        }
    });

    // Close mobile drawer on item select
    document.getElementById("app").classList.remove("sidebar-open");
    
    // Reset attached file preview inside composer
    removeAttachedFile();
    
    // Restore Active Document Type for the loaded conversation
    const activeChat = conversations.find(c => c.id === id);
    if (activeChat && activeChat.document_type) {
        selectedDocumentType = activeChat.document_type;
    } else {
        selectedDocumentType = "Legal Agreement";
    }
    updateActiveDocumentTypeTab(selectedDocumentType);
    updateClassificationBanner();
    
    // Fetch and render messages history
    messagesContainer.innerHTML = `<div class="zero-state"><i class="fa-solid fa-spinner fa-spin welcome-icon"></i><p>Loading messages...</p></div>`;
    
    try {
        const response = await fetch(`${BASE_URL}/api/conversations/${id}/messages`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        
        if (response.ok) {
            const history = await response.json();
            renderMessages(history);
            // Refresh info panel view for the loaded conversation
            updateInfoPanelForActiveConversation();
            updateClassificationBanner();
        } else {
            messagesContainer.innerHTML = `<div class="zero-state"><p class="text-danger">Failed to load conversation history.</p></div>`;
        }
    } catch (err) {
        console.error("Messages fetch error:", err);
    }
}

async function handleNewChat() {
    activeConversationId = null;
    activeChatTitle.innerText = "New Chat";
    
    // Reset sidebar highlights
    document.querySelectorAll("#recent-chats-list .sidebar-list-item").forEach(item => {
        item.classList.remove("active");
    });
    
    // Reset composer state
    removeAttachedFile();
    chatInput.value = "";
    chatInput.style.height = "auto";
    sendBtn.classList.remove("active");
    updateClassificationBanner();
    
    // Show zero state
    messagesContainer.innerHTML = `
        <div id="zero-state" class="zero-state">
            <i class="fa-solid fa-scale-balanced welcome-icon"></i>
            <h1>How can LegalLens assist you today?</h1>
            <p>Upload files or prompt directly to analyze contracts, extract terms, verify dates, or conduct general research.</p>
        </div>
    `;
    
    // Create new conversation backend
    try {
        const response = await fetch(`${BASE_URL}/api/conversations`, {
            method: "POST",
            headers: { 
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ title: "New Chat" })
        });
        
        if (response.ok) {
            const chat = await response.json();
            activeConversationId = chat.id;
            // Refetch list and load
            await fetchConversations();
            loadConversation(chat.id, "New Chat");
        }
    } catch (err) {
        console.error("Error creating new chat:", err);
    }
}

async function deleteChat(id) {
    if (!confirm("Are you sure you want to delete this chat?")) return;
    
    try {
        const response = await fetch(`${BASE_URL}/api/conversations/${id}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${token}` }
        });
        
        if (response.ok) {
            if (activeConversationId === id) {
                handleNewChat();
            } else {
                fetchConversations();
            }
        }
    } catch (err) {
        console.error("Delete conversation error:", err);
    }
}

// ==========================================================================
// FILE UPLOADER & DOCUMENTS LIBRARY
// ==========================================================================

async function fetchDocumentLibrary() {
    try {
        const response = await fetch(`${BASE_URL}/api/documents/search?query=`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (response.ok) {
            libraryDocuments = await response.json();
            renderDocumentsLibrary(libraryDocuments);
            updateInfoPanelForActiveConversation();
        }
    } catch (err) {
        console.error("Error fetching library documents:", err);
    }
}

function renderDocumentsLibrary(docs) {
    documentsLibraryList.innerHTML = "";
    if (docs.length === 0) {
        documentsLibraryList.innerHTML = `<div class="list-placeholder">No documents uploaded</div>`;
        return;
    }
    
    docs.forEach(doc => {
        const li = document.createElement("li");
        li.className = "sidebar-list-item";
        li.title = `Attached to conversation: ${doc.conversation_id}`;
        
        const sizeKB = Math.round(doc.file_size / 1024);
        
        let checkboxMarkup = "";
        if (compareMode) {
            const isChecked = selectedCompareDocs.includes(doc.id) ? 'checked' : '';
            checkboxMarkup = `<input type="checkbox" class="sidebar-list-item-checkbox" data-id="${doc.id}" ${isChecked} onclick="event.stopPropagation(); toggleCompareDocSelection('${doc.id}')">`;
        }
        
        li.innerHTML = `
            ${checkboxMarkup}
            <i class="fa-solid fa-file-pdf"></i>
            <span class="list-item-title">${escapeHTML(doc.filename)} (${sizeKB} KB)</span>
        `;
        
        li.addEventListener("click", () => {
            if (compareMode) {
                toggleCompareDocSelection(doc.id);
            } else {
                attachedFile = {
                    id: doc.id,
                    name: doc.filename,
                    size: doc.file_size
                };
                showComposerFilePill();
            }
        });
        
        documentsLibraryList.appendChild(li);
    });
}

async function handleDocumentSearch() {
    const q = docSearchInput.value.trim();
    if (!q) {
        removeSearchResultsOverlay();
        fetchDocumentLibrary();
        return;
    }
    try {
        const response = await fetch(`${BASE_URL}/api/documents/search?query=${q}`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (response.ok) {
            const results = await response.json();
            if (results.length > 0 && results[0].content !== undefined) {
                showSearchResultsOverlay(results);
            } else {
                removeSearchResultsOverlay();
                renderDocumentsLibrary(results);
            }
        }
    } catch (err) {
        console.error("Search API error:", err);
    }
}

async function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    
    // Ensure activeConversationId is initialized
    if (!activeConversationId) {
        await handleNewChat();
    }
    
    // UI Loading state
    attachedFile = {
        name: file.name,
        size: file.size
    };
    showComposerFilePill();
    updateProgressStatus("Uploading...", true);
    fileUploadProgress.classList.remove("hidden");
    
    const formData = new FormData();
    formData.append("file", file);
    formData.append("conversation_id", activeConversationId);
    formData.append("language", selectedLanguage || "English");
    
    try {
        const response = await fetch(`${BASE_URL}/api/documents/upload`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` },
            body: formData
        });
        
        if (response.ok) {
            const docRecord = await response.json();
            if (attachedFile) {
                attachedFile.id = docRecord.id;
            }
            
            updateProgressStatus("Uploaded ✓", false, "fa-circle-check");
            
            if (docRecord.status === 'processing') {
                setTimeout(() => {
                    updateProgressStatus("Processing document...", true, "fa-spinner");
                }, 1000);
                pollDocumentStatus(docRecord.id);
            } else if (docRecord.status === 'ready') {
                // Cache hit!
                updateProgressStatus("Ready to chat ✓", false, "fa-circle-check");
                setTimeout(() => {
                    fileUploadProgress.classList.add("hidden");
                }, 1500);
                fetchDocumentLibrary();
            }
        } else {
            const errorData = await response.json();
            alert(`Upload failed: ${errorData.detail || "Unable to process document"}`);
            removeAttachedFile();
        }
    } catch (err) {
        console.error("File upload failed:", err);
        alert("Upload failed. Server is unreachable.");
        removeAttachedFile();
    }
}

function showComposerFilePill() {
    if (!attachedFile) return;
    
    filePillName.innerText = attachedFile.name;
    const sizeKB = Math.round(attachedFile.size / 1024);
    filePillSize.innerText = `${sizeKB} KB`;
    
    attachedFilePreview.classList.remove("hidden");
}

function removeAttachedFile() {
    attachedFile = null;
    fileUploader.value = "";
    attachedFilePreview.classList.add("hidden");
    fileUploadProgress.classList.add("hidden");
}

// ==========================================================================
// VOICE TRANSCRIBER INTERFACES
// ==========================================================================

function setupSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        voiceBtn.style.display = "none"; // Hide if not supported
        return;
    }
    
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US"; // default, can change depending on dialect
    
    recognition.onstart = () => {
        voiceBtn.classList.add("voice-active");
    };
    
    recognition.onerror = (e) => {
        console.error("Speech recognition error:", e.error);
        voiceBtn.classList.remove("voice-active");
    };
    
    recognition.onend = () => {
        voiceBtn.classList.remove("voice-active");
    };
    
    recognition.onresult = (e) => {
        const transcript = e.results[0][0].transcript;
        chatInput.value = (chatInput.value + " " + transcript).trim();
        // Trigger resize
        chatInput.dispatchEvent(new Event("input"));
    };
    
    voiceBtn.addEventListener("click", () => {
        if (voiceBtn.classList.contains("voice-active")) {
            recognition.stop();
        } else {
            recognition.start();
        }
    });
}

// ==========================================================================
// MESSAGES RENDERING & MARKDOWN COMPILATION
// ==========================================================================

function renderMessages(messages) {
    messagesContainer.innerHTML = "";
    if (messages.length === 0) {
        messagesContainer.innerHTML = `
            <div id="zero-state" class="zero-state">
                <i class="fa-solid fa-scale-balanced welcome-icon"></i>
                <h1>Welcome to LegalLens</h1>
                <p>Upload a document and start typing to analyze legal agreements, detect risks, extract clauses or obligations.</p>
            </div>
        `;
        return;
    }
    
    messages.forEach(msg => {
        appendMessageToContainer(msg.sender, msg.content, msg.file_name, msg.file_size);
    });
    
    scrollToBottom();
}

function appendMessageToContainer(sender, content, attachedFileName = null, attachedFileSize = null, sources = []) {
    // Clear zero state if present
    const zs = document.getElementById("zero-state");
    if (zs) zs.remove();
    
    const row = document.createElement("div");
    row.className = `message-row ${sender}-row`;
    
    const avatarIcon = sender === "user" ? '<i class="fa-regular fa-user"></i>' : '<i class="fa-solid fa-scale-balanced"></i>';
    
    // Compile markdown
    const formattedBody = sender === "assistant" ? compileMarkdown(content) : escapeHTML(content).replace(/\n/g, "<br>");
    
    // Add file icon in user messages if present
    let inlineFileMarkup = "";
    if (sender === "user" && attachedFileName) {
        const sizeKB = Math.round(attachedFileSize / 1024);
        inlineFileMarkup = `
            <div class="inline-file-pill">
                <i class="fa-solid fa-file-pdf"></i>
                <span>${escapeHTML(attachedFileName)} (${sizeKB} KB)</span>
            </div>
        `;
    }
    
    // Sources citation footer markup
    // Sources citation footer markup (Feature 11)
    let sourcesMarkup = "";
    if (sender === "assistant" && sources && sources.length > 0) {
        const tags = sources.map(s => {
            if (s.url === "#") {
                return `
                    <span class="source-tag" style="cursor: default;" title="${escapeHTML(s.title)}">
                        <i class="fa-solid fa-file-invoice"></i> ${escapeHTML(s.title)}
                    </span>
                `;
            }
            return `
                <a href="${s.url}" target="_blank" class="source-tag" title="${escapeHTML(s.title)}">
                    <i class="fa-solid fa-link"></i> ${escapeHTML(s.title)}
                </a>
            `;
        }).join("");
        sourcesMarkup = `
            <div class="message-sources">
                <div class="sources-title">Sources</div>
                <div class="sources-list">${tags}</div>
            </div>
        `;
    }

    row.innerHTML = `
        <div class="message-cell">
            <div class="message-avatar">${avatarIcon}</div>
            <div class="message-content">
                ${inlineFileMarkup}
                <div class="message-bubble">${formattedBody} ${sourcesMarkup}</div>
            </div>
        </div>
    `;
    
    messagesContainer.appendChild(row);
}

// Light Custom Markdown compiler supporting headers, lists, tables, pre/code
function compileMarkdown(text) {
    if (!text) return "";
    let html = text;
    
    // Escape HTML entities to prevent rendering issues
    html = html
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
        
    // 1. Code blocks
    html = html.replace(/```([\s\S]*?)```/g, (match, code) => {
        return `<pre><code>${code.trim()}</code></pre>`;
    });
    
    // 2. Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // 3. Bold / Italics
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    
    // 4. Line by line parsing for headers, lists, tables, paragraphs
    const lines = html.split("\n");
    let output = [];
    let inList = false;
    let listType = null; // 'ul' or 'ol'
    let inTable = false;
    let tableHeaders = [];
    let tableRows = [];
    
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trim();
        
        // Handle preformatted segments
        if (line.startsWith("<pre>") || line.endsWith("</pre>")) {
            output.push(lines[i]);
            continue;
        }
        
        // Handle Table parser: | col1 | col2 |
        if (line.startsWith("|")) {
            inTable = true;
            const cells = line.split("|").map(c => c.trim()).filter((c, idx, arr) => idx > 0 && idx < arr.length - 1);
            
            // Check if this is the separator row: | --- | --- |
            if (cells.every(c => c.startsWith("-"))) {
                continue;
            }
            
            if (tableHeaders.length === 0) {
                tableHeaders = cells;
            } else {
                tableRows.push(cells);
            }
            continue;
        } else if (inTable && !line.startsWith("|")) {
            // Close table
            output.push(renderTableHTML(tableHeaders, tableRows));
            tableHeaders = [];
            tableRows = [];
            inTable = false;
        }
        
        // Handle Headers
        if (line.startsWith("### ")) {
            closeList(output, inList, listType);
            inList = false;
            output.push(`<h3>${line.substring(4)}</h3>`);
            continue;
        }
        if (line.startsWith("## ")) {
            closeList(output, inList, listType);
            inList = false;
            output.push(`<h2>${line.substring(3)}</h2>`);
            continue;
        }
        if (line.startsWith("# ")) {
            closeList(output, inList, listType);
            inList = false;
            output.push(`<h1>${line.substring(2)}</h1>`);
            continue;
        }
        
        // Handle Unordered Lists (- list item)
        if (line.startsWith("- ") || line.startsWith("* ")) {
            if (!inList || listType !== 'ul') {
                closeList(output, inList, listType);
                output.push("<ul>");
                inList = true;
                listType = 'ul';
            }
            output.push(`<li>${line.substring(2)}</li>`);
            continue;
        }
        
        // Handle Ordered Lists (1. list item)
        if (/^\d+\.\s/.test(line)) {
            const content = line.replace(/^\d+\.\s/, "");
            if (!inList || listType !== 'ol') {
                closeList(output, inList, listType);
                output.push("<ol>");
                inList = true;
                listType = 'ol';
            }
            output.push(`<li>${content}</li>`);
            continue;
        }
        
        // Close list if line is empty and we were in a list
        if (line === "" && inList) {
            closeList(output, inList, listType);
            inList = false;
            listType = null;
            continue;
        }
        
        // Paragraphs / raw lines
        if (line !== "") {
            closeList(output, inList, listType);
            inList = false;
            output.push(`<p>${lines[i]}</p>`);
        }
    }
    
    // Cleanup dangling lists and tables
    closeList(output, inList, listType);
    if (inTable) {
        output.push(renderTableHTML(tableHeaders, tableRows));
    }
    
    return output.join("\n");
}

function closeList(output, inList, listType) {
    if (inList) {
        output.push(listType === 'ul' ? "</ul>" : "</ol>");
    }
}

function renderTableHTML(headers, rows) {
    let html = "<table><thead><tr>";
    headers.forEach(h => {
        html += `<th>${h}</th>`;
    });
    html += "</tr></thead><tbody>";
    rows.forEach(r => {
        html += "<tr>";
        r.forEach(c => {
            html += `<td>${c}</td>`;
        });
        html += "</tr>";
    });
    html += "</tbody></table>";
    return html;
}

function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// ==========================================================================
// CHAT MESSAGE PIPELINE
// ==========================================================================

async function handleMessageSubmit(e) {
    e.preventDefault();
    
    const prompt = chatInput.value.trim();
    if (!prompt) return;
    
    // Ensure activeConversationId is initialized
    if (!activeConversationId) {
        await handleNewChat();
    }
    
    // Upload check
    if (fileUploadProgress.classList.contains("hidden") === false) {
        const spanText = fileUploadProgress.querySelector("span") ? fileUploadProgress.querySelector("span").innerText : "";
        if (spanText === "Uploading...") {
            alert("Document uploading in progress. Please wait...");
            return;
        }
    }
    
    // Capture state values
    const currentFile = attachedFile;
    const currentConvId = activeConversationId;
    
    // 1. Render User Message Inline in Chat
    appendMessageToContainer("user", prompt, currentFile ? currentFile.name : null, currentFile ? currentFile.size : null);
    scrollToBottom();
    
    // Reset composer input layout
    chatInput.value = "";
    chatInput.style.height = "auto";
    sendBtn.classList.remove("active");
    removeAttachedFile();
    
    // 2. Render Loading skeleton bubble
    const loadingRow = document.createElement("div");
    loadingRow.className = "message-row assistant-row";
    loadingRow.id = "assistant-loading-bubble";
    loadingRow.innerHTML = `
        <div class="message-cell">
            <div class="message-avatar"><i class="fa-solid fa-scale-balanced"></i></div>
            <div class="message-content">
                <div class="message-bubble ai-loading-bubble">
                    <span style="font-size: 0.85rem; color: var(--text-muted); margin-right: 0.5rem;">LegalLens is thinking</span>
                    <div class="dot-spin"></div>
                    <div class="dot-spin"></div>
                    <div class="dot-spin"></div>
                </div>
            </div>
        </div>
    `;
    messagesContainer.appendChild(loadingRow);
    scrollToBottom();
    
    // Update active chat title in recent chats list if it was a default "New Chat" title
    let isDefaultTitle = false;
    const activeChat = conversations.find(c => c.id === currentConvId);
    if (activeChat && activeChat.title === "New Chat") {
        isDefaultTitle = true;
    }
    
    // 3. Make POST streaming request to backend
    try {
        const payload = {
            prompt: prompt,
            file_id: currentFile ? currentFile.id : null,
            search_grounding: searchGrounding,
            language: selectedLanguage
        };
        
        const response = await fetch(`${BASE_URL}/api/conversations/${currentConvId}/send`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });
        
        // Remove loading bubble
        if (document.getElementById("assistant-loading-bubble")) {
            document.getElementById("assistant-loading-bubble").remove();
        }
        
        if (response.ok) {
            const msgRow = appendEmptyAssistantMessageContainer();
            const bubbleText = msgRow.querySelector(".message-bubble-text");
            const sourcesList = msgRow.querySelector(".sources-list");
            const sourcesTitle = msgRow.querySelector(".message-sources");
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let accumulatedText = "";
            let sources = [];
            
            let buffer = "";
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop(); // Save partial line
                
                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed || !trimmed.startsWith("data: ")) continue;
                    
                    try {
                        const jsonStr = trimmed.substring(6);
                        const data = JSON.parse(jsonStr);
                        
                        if (data.text) {
                            accumulatedText += data.text;
                            bubbleText.innerHTML = compileMarkdown(accumulatedText);
                            scrollToBottom();
                        }
                        if (data.sources) {
                            sources = data.sources;
                            renderCitations(sources, sourcesTitle, sourcesList);
                            scrollToBottom();
                        }
                    } catch (e) {
                        console.error("Stream parse error:", e);
                    }
                }
            }
            
            // Clean up remainder of the buffer
            if (buffer.trim().startsWith("data: ")) {
                try {
                    const jsonStr = buffer.trim().substring(6);
                    const data = JSON.parse(jsonStr);
                    if (data.text) {
                        accumulatedText += data.text;
                        bubbleText.innerHTML = compileMarkdown(accumulatedText);
                    }
                    if (data.sources) {
                        sources = data.sources;
                        renderCitations(sources, sourcesTitle, sourcesList);
                    }
                } catch (e) {}
            }
            
            // If the chat title was default, update title using the user's first prompt
            if (isDefaultTitle) {
                const newTitle = prompt.length > 25 ? prompt.substring(0, 25) + "..." : prompt;
                updateChatTitle(currentConvId, newTitle);
            }
        } else {
            const errData = await response.json();
            appendMessageToContainer("assistant", `**Error**: ${errData.detail || "Unable to retrieve response from Gemini. Please verify configuration."}`);
            scrollToBottom();
        }
    } catch (err) {
        console.error("Chat completion stream API failed:", err);
        if (document.getElementById("assistant-loading-bubble")) {
            document.getElementById("assistant-loading-bubble").remove();
        }
        appendMessageToContainer("assistant", "**Error**: AI service is not configured or network connection is down.");
        scrollToBottom();
    }
}

async function updateChatTitle(convId, newTitle) {
    try {
        const response = await fetch(`${BASE_URL}/api/conversations/${convId}`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ title: newTitle })
        });
        
        if (response.ok) {
            // Update UI title and list
            activeChatTitle.innerText = newTitle;
            fetchConversations();
        }
    } catch (err) {
        console.error("Title patch API error:", err);
    }
}

// Helpers
function escapeHTML(text) {
    if (text === null || text === undefined) return "";
    return text
        .toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Update Active Tab in Document Navigation Bar
function updateActiveDocumentTypeTab(docType) {
    const tabs = document.querySelectorAll(".doc-type-tab");
    tabs.forEach(tab => {
        if (tab.dataset.type === docType) {
            tab.classList.add("active");
            tab.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
        } else {
            tab.classList.remove("active");
        }
    });
}

// Select Document Type and Sync to Backend (Feature 1 & 12)
async function selectDocumentType(docType) {
    selectedDocumentType = docType;
    updateActiveDocumentTypeTab(docType);
    updateClassificationBanner();

    if (activeConversationId) {
        try {
            const response = await fetch(`${BASE_URL}/api/conversations/${activeConversationId}/document-type`, {
                method: "PATCH",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({ document_type: docType })
            });
            if (response.ok) {
                // Update local conversation state so reloading does not reset it
                const chat = conversations.find(c => c.id === activeConversationId);
                if (chat) {
                    chat.document_type = docType;
                }
                
                // Check if active document exists and start polling for re-analysis
                const activeDocs = libraryDocuments.filter(d => d.conversation_id === activeConversationId);
                if (activeDocs.length > 0) {
                    const activeDoc = activeDocs[activeDocs.length - 1];
                    updateProgressStatus("Re-analyzing...", true, "fa-spinner");
                    fileUploadProgress.classList.remove("hidden");
                    pollDocumentStatus(activeDoc.id);
                }
            }
        } catch (e) {
            console.error("Failed to sync document type mode:", e);
        }
    }
}

// Render dynamic mode / classification feedback banner
function updateClassificationBanner() {
    const banner = document.getElementById("classification-banner");
    if (!banner) return;
    
    if (!activeConversationId) {
        banner.classList.add("hidden");
        return;
    }
    
    const activeDocs = libraryDocuments.filter(d => d.conversation_id === activeConversationId);
    if (activeDocs.length > 0) {
        const doc = activeDocs[activeDocs.length - 1];
        const docType = doc.detected_type || selectedDocumentType || "Legal Agreement";
        const confidence = doc.confidence;
        
        banner.classList.remove("hidden");
        
        if (confidence !== null && confidence !== undefined && confidence < 70) {
            banner.className = "classification-banner warning-banner";
            banner.innerHTML = `
                <div class="banner-text">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                    <span>Document type may be unclear. AI is currently analyzing this document as an <strong>${escapeHTML(docType)}</strong>.</span>
                </div>
                <span class="banner-action-desc">Click any category tab above to override manually</span>
            `;
        } else {
            banner.className = "classification-banner info-banner";
            banner.innerHTML = `
                <div class="banner-text">
                    <i class="fa-solid fa-circle-info"></i>
                    <span>AI is currently analyzing this document as an <strong>${escapeHTML(docType)}</strong>.</span>
                </div>
                <span class="banner-action-desc">Automatic mode active</span>
            `;
        }
    } else {
        banner.classList.add("hidden");
    }
}

// Render Collapsible Info Panel contents (Feature 10)
function renderInfoPanelPlaceholder() {
    const infoPanelContent = document.getElementById("info-panel-content");
    infoPanelContent.innerHTML = `
        <div class="panel-placeholder">
            <i class="fa-solid fa-file-shield placeholder-icon"></i>
            <p>Upload or select a document in the active chat to view dynamic intelligence and extracted fields.</p>
        </div>
    `;
}

function updateDocDashboardBar(doc) {
    const bar = document.getElementById("doc-dashboard-bar");
    if (!bar) return;
    if (!doc) {
        bar.classList.add("hidden");
        return;
    }
    bar.classList.remove("hidden");
    const badge = document.getElementById("dashboard-doc-badge");
    const title = document.getElementById("dashboard-doc-title");
    const conf = document.getElementById("dashboard-doc-confidence");
    
    if (badge) badge.innerText = doc.detected_type || selectedDocumentType || "Legal Agreement";
    if (title) title.innerText = doc.filename || "Uploaded Document";
    if (conf) {
        const cVal = doc.confidence ? `${Math.round(doc.confidence)}%` : "95%";
        conf.innerHTML = `<i class="fa-solid fa-circle-check"></i> High (${cVal})`;
    }
}

async function handleExplainFullDocument() {
    const activeDocs = libraryDocuments.filter(d => d.conversation_id === activeConversationId);
    if (!activeDocs.length) {
        alert("Please upload a document to explain.");
        return;
    }
    const doc = activeDocs[0];
    const userPrompt = "Explain full document section-by-section";
    appendMessageToContainer("user", userPrompt, doc.filename, doc.file_size);
    scrollToBottom();
    
    const assistantRow = appendEmptyAssistantMessageContainer();
    const bubbleText = assistantRow.querySelector(".message-bubble-text");
    bubbleText.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generating section-by-section explanation...';
    scrollToBottom();
    
    try {
        const response = await fetch(`${BASE_URL}/api/documents/${doc.id}/explain-full`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({
                document_type: doc.detected_type || selectedDocumentType,
                language: selectedLanguage || "English"
            })
        });
        if (response.ok) {
            const data = await response.json();
            bubbleText.innerHTML = parseMarkdownToHTML(data.explanation || "Full explanation generated.");
        } else {
            bubbleText.innerHTML = "Unable to generate section-by-section breakdown.";
        }
    } catch (e) {
        bubbleText.innerHTML = "Failed to communicate with document intelligence server.";
    }
    scrollToBottom();
}

async function handleWhatShouldIKnow() {
    const activeDocs = libraryDocuments.filter(d => d.conversation_id === activeConversationId);
    if (!activeDocs.length) {
        alert("Please upload a document first.");
        return;
    }
    const doc = activeDocs[0];
    const userPrompt = "What should I know from this document?";
    appendMessageToContainer("user", userPrompt, doc.filename, doc.file_size);
    scrollToBottom();
    
    const assistantRow = appendEmptyAssistantMessageContainer();
    const bubbleText = assistantRow.querySelector(".message-bubble-text");
    bubbleText.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generating What Should I Know briefing...';
    scrollToBottom();
    
    try {
        const response = await fetch(`${BASE_URL}/api/documents/${doc.id}/what-should-i-know?language=${encodeURIComponent(selectedLanguage || 'English')}`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (response.ok) {
            const data = await response.json();
            let md = "### 💡 WHAT SHOULD I KNOW FROM THIS DOCUMENT?\n\n";
            if (data.top_things_to_know && data.top_things_to_know.length > 0) {
                md += "#### 🌟 TOP 5 THINGS TO KNOW\n";
                data.top_things_to_know.forEach((item, idx) => {
                    md += `${idx + 1}. **${item}**\n`;
                });
                md += "\n";
            }
            if (data.action_items && data.action_items.length > 0) {
                md += "#### 🚀 WHAT TO DO NEXT\n";
                data.action_items.forEach(item => {
                    md += `• [ ] ${item}\n`;
                });
                md += "\n";
            }
            bubbleText.innerHTML = parseMarkdownToHTML(md);
        } else {
            bubbleText.innerHTML = "Unable to retrieve document briefing.";
        }
    } catch (e) {
        bubbleText.innerHTML = "Failed to communicate with document intelligence server.";
    }
    scrollToBottom();
}

function handleQuickRisks() {
    chatInput.value = "What are the major risks, penalties, and warnings in this document?";
    handleMessageSubmit(new Event("submit"));
}

function handleNextActions() {
    chatInput.value = "What specific next actions should I take for this document?";
    handleMessageSubmit(new Event("submit"));
}

function updateInfoPanelForActiveConversation() {
    if (!activeConversationId) {
        renderInfoPanelPlaceholder();
        updateDocDashboardBar(null);
        return;
    }
    const activeDocs = libraryDocuments.filter(d => d.conversation_id === activeConversationId);
    if (activeDocs.length > 0) {
        renderImportantInformation(activeDocs[0]);
        updateDocDashboardBar(activeDocs[0]);
    } else {
        renderInfoPanelPlaceholder();
        updateDocDashboardBar(null);
    }
}

function renderImportantInformation(doc) {
    const infoPanelContent = document.getElementById("info-panel-content");
    if (!doc.summary && !doc.extracted_info) {
        renderInfoPanelPlaceholder();
        return;
    }
    
    let analysis = {};
    try {
        analysis = JSON.parse(doc.extracted_info || "{}");
    } catch (e) {
        console.error("Failed to parse document analysis:", e);
    }
    
    const extractedFields = analysis.extracted_info || {};
    const missingInfo = analysis.missing_info || [];
    const actionItems = analysis.action_items || [];
    
    let fieldsHTML = "";
    if (Object.keys(extractedFields).length > 0) {
        fieldsHTML = `<div class="panel-section">
            <div class="panel-section-title">Extracted Details</div>
            <div class="extracted-fields-list">`;
        for (const [label, val] of Object.entries(extractedFields)) {
            const isNotFound = val === "Not found in the document.";
            fieldsHTML += `
                <div class="extracted-field-item">
                    <div class="extracted-field-label">${escapeHTML(label)}</div>
                    <div class="extracted-field-value ${isNotFound ? 'not-found' : ''}">${escapeHTML(val)}</div>
                </div>`;
        }
        fieldsHTML += `</div></div>`;
    }
    
    let missingHTML = "";
    if (missingInfo.length > 0) {
        missingHTML = `<div class="panel-section">
            <div class="panel-section-title">⚠️ Missing / Unclear Info</div>`;
        missingInfo.forEach(item => {
            missingHTML += `
                <div class="missing-info-item">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                    <span>${escapeHTML(item)}</span>
                </div>`;
        });
        missingHTML += `</div>`;
    } else {
        missingHTML = `<div class="panel-section">
            <div class="panel-section-title">⚠️ Missing / Unclear Info</div>
            <div class="list-placeholder">No missing info detected.</div>
        </div>`;
    }
    
    let actionsHTML = "";
    if (actionItems.length > 0) {
        actionsHTML = `<div class="panel-section">
            <div class="panel-section-title">Action Items</div>
            <div class="action-items-list">`;
        actionItems.forEach((item, idx) => {
            actionsHTML += `
                <label class="action-item-checkbox-wrapper">
                    <input type="checkbox" id="action-item-${idx}">
                    <span>${escapeHTML(item)}</span>
                </label>`;
        });
        actionsHTML += `</div></div>`;
    } else {
        actionsHTML = `<div class="panel-section">
            <div class="panel-section-title">Action Items</div>
            <div class="list-placeholder">No action items found.</div>
        </div>`;
    }
    
    infoPanelContent.innerHTML = `
        <div class="doc-info-active-meta">
            <div class="sidebar-list-item active" style="margin-bottom:1rem; border-left:none; background:rgba(99,102,241,0.05)">
                <i class="fa-solid fa-file-pdf"></i>
                <span class="list-item-title">${escapeHTML(doc.filename)}</span>
            </div>
        </div>
        ${fieldsHTML}
        ${missingHTML}
        ${actionsHTML}
    `;
}

// Compare Documents Mode logic (Feature 5)
function toggleCompareMode() {
    compareMode = !compareMode;
    const compareModeBtn = document.getElementById("compare-mode-btn");
    
    if (compareMode) {
        compareModeBtn.classList.add("active");
        selectedCompareDocs = [];
        
        document.getElementById("comparison-workspace").classList.remove("hidden");
        document.getElementById("messages-container").classList.add("hidden");
        document.querySelector(".composer-container").classList.add("hidden");
        
        document.getElementById("comparison-results-container").innerHTML = `
            <div class="comparison-placeholder">
                <i class="fa-solid fa-file-invoice placeholder-icon"></i>
                <p>Select documents from the sidebar checkboxes and click 'Compare Selected' to start.</p>
            </div>
        `;
    } else {
        exitCompareMode();
    }
    
    renderDocumentsLibrary(libraryDocuments);
}

function exitCompareMode() {
    compareMode = false;
    selectedCompareDocs = [];
    
    const compareModeBtn = document.getElementById("compare-mode-btn");
    if (compareModeBtn) compareModeBtn.classList.remove("active");
    
    const compWorkspace = document.getElementById("comparison-workspace");
    if (compWorkspace) compWorkspace.classList.add("hidden");
    
    const msgContainer = document.getElementById("messages-container");
    if (msgContainer) msgContainer.classList.remove("hidden");
    
    const composer = document.querySelector(".composer-container");
    if (composer) composer.classList.remove("hidden");
    
    renderDocumentsLibrary(libraryDocuments);
    scrollToBottom();
}

function toggleCompareDocSelection(id) {
    const idx = selectedCompareDocs.indexOf(id);
    if (idx > -1) {
        selectedCompareDocs.splice(idx, 1);
    } else {
        selectedCompareDocs.push(id);
    }
    renderDocumentsLibrary(libraryDocuments);
}

async function runComparison() {
    if (selectedCompareDocs.length < 2) {
        alert("Please select at least two documents to compare.");
        return;
    }
    
    const resultsContainer = document.getElementById("comparison-results-container");
    resultsContainer.innerHTML = `
        <div class="comparison-placeholder">
            <i class="fa-solid fa-spinner fa-spin placeholder-icon"></i>
            <p>Generating dynamic comparison table from actual document contents. Please wait...</p>
        </div>
    `;
    
    try {
        const response = await fetch(`${BASE_URL}/api/documents/compare`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({
                document_ids: selectedCompareDocs,
                language: selectedLanguage,
                document_type: selectedDocumentType
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            renderComparisonResults(data);
        } else {
            const err = await response.json();
            resultsContainer.innerHTML = `
                <div class="comparison-placeholder text-danger">
                    <i class="fa-solid fa-triangle-exclamation placeholder-icon"></i>
                    <p>Comparison failed: ${err.detail || "Unable to compare documents."}</p>
                </div>
            `;
        }
    } catch (e) {
        console.error("Comparison execution error:", e);
        resultsContainer.innerHTML = `
            <div class="comparison-placeholder text-danger">
                <i class="fa-solid fa-triangle-exclamation placeholder-icon"></i>
                <p>Comparison failed. Server is unreachable.</p>
            </div>
        `;
    }
}

function renderComparisonResults(data) {
    const resultsContainer = document.getElementById("comparison-results-container");
    
    const tableHTML = compileMarkdown(data.comparison_table);
    const keyDiffsHTML = compileMarkdown(data.key_differences || "No key differences found.");
    const importantChangesHTML = compileMarkdown(data.important_changes || "No important changes found.");
    const similaritiesHTML = compileMarkdown(data.similarities || "No similarities found.");
    const missingHTML = compileMarkdown(data.missing_information || "No missing information found.");
    
    resultsContainer.innerHTML = `
        <div class="table-responsive-container">
            ${tableHTML}
        </div>
        
        <div class="comparison-insights">
            <div class="insight-card">
                <h4><i class="fa-solid fa-circle-minus"></i> Key Differences</h4>
                <div>${keyDiffsHTML}</div>
            </div>
            <div class="insight-card">
                <h4><i class="fa-solid fa-circle-check"></i> Similarities</h4>
                <div>${similaritiesHTML}</div>
            </div>
            <div class="insight-card">
                <h4><i class="fa-solid fa-circle-exclamation"></i> Important Changes</h4>
                <div>${importantChangesHTML}</div>
            </div>
            <div class="insight-card">
                <h4><i class="fa-solid fa-circle-question"></i> Missing Information</h4>
                <div>${missingHTML}</div>
            </div>
        </div>
    `;
}

// Natural language search dropdown helpers
let searchOverlay = null;

function showSearchResultsOverlay(results) {
    removeSearchResultsOverlay();
    
    if (results.length === 0 || !results[0].content) {
        return;
    }
    
    searchOverlay = document.createElement("div");
    searchOverlay.className = "search-results-overlay scrollbar-custom";
    
    const header = document.createElement("div");
    header.className = "search-results-header";
    header.innerHTML = `<span>Semantic Search Matches</span> <button onclick="removeSearchResultsOverlay()">&times;</button>`;
    searchOverlay.appendChild(header);
    
    const list = document.createElement("ul");
    list.className = "search-results-list";
    
    results.forEach(res => {
        const item = document.createElement("li");
        item.className = "search-result-item";
        
        item.innerHTML = `
            <div class="search-result-docname">${escapeHTML(res.filename)}</div>
            <div class="search-result-snippet">"${escapeHTML(res.content)}"</div>
            <div class="search-result-page">Page ${res.page_number} • Match ${(res.similarity * 100).toFixed(0)}%</div>
        `;
        
        item.addEventListener("click", () => {
            removeSearchResultsOverlay();
            docSearchInput.value = "";
            const chat = conversations.find(c => c.id === res.conversation_id);
            const title = chat ? chat.title : "Active Chat";
            loadConversation(res.conversation_id, title);
        });
        
        list.appendChild(item);
    });
    
    searchOverlay.appendChild(list);
    
    const searchBox = document.querySelector(".sidebar-search");
    searchBox.appendChild(searchOverlay);
}

function removeSearchResultsOverlay() {
    if (searchOverlay) {
        searchOverlay.remove();
        searchOverlay = null;
    }
}

// Performance Optimization Helper Functions
function updateProgressStatus(text, spin = true, iconClass = "fa-spinner") {
    const span = fileUploadProgress.querySelector("span");
    const icon = fileUploadProgress.querySelector("i");
    if (span) span.innerText = text;
    if (icon) {
        icon.className = `fa-solid ${iconClass} ${spin ? 'fa-spin' : ''}`;
    }
}

function pollDocumentStatus(docId) {
    const interval = setInterval(async () => {
        try {
            const response = await fetch(`${BASE_URL}/api/documents/${docId}`, {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (response.ok) {
                const doc = await response.json();
                
                // Handle mismatch state if present
                if (doc.status === 'mismatch') {
                    clearInterval(interval);
                    if (attachedFile) {
                        attachedFile.detectedType = doc.detected_type;
                    }
                    mismatchMessageText.innerText = doc.mismatch_message || `This document appears to be an ${doc.detected_type} rather than the selected type.`;
                    mismatchModal.classList.remove("hidden");
                    return;
                }
                
                if (doc.status === 'ready') {
                    updateProgressStatus("Ready to chat ✓", false, "fa-circle-check");
                    setTimeout(() => {
                        fileUploadProgress.classList.add("hidden");
                    }, 1500);
                    
                    // Refresh library documents
                    await fetchDocumentLibrary();
                    
                    // Automatically update active tab mode to detected type
                    if (doc.detected_type && doc.detected_type !== selectedDocumentType) {
                        selectedDocumentType = doc.detected_type;
                        updateActiveDocumentTypeTab(doc.detected_type);
                    }
                    updateClassificationBanner();
                    
                    // Parse analysis to check if deep analysis is complete
                    let hasExtractedInfo = false;
                    try {
                        const analysis = JSON.parse(doc.extracted_info || "{}");
                        if (analysis.extracted_info && Object.keys(analysis.extracted_info).length > 0) {
                            hasExtractedInfo = true;
                        }
                    } catch (e) {}
                    
                    if (hasExtractedInfo) {
                        // Deep analysis complete! Stop polling
                        clearInterval(interval);
                        if (activeConversationId === doc.conversation_id) {
                            loadConversation(activeConversationId, activeChatTitle.innerText);
                        }
                    } else {
                        // Quick summary available, load conversation once if not already done
                        if (loadedQuickSummaryForDoc !== docId && activeConversationId === doc.conversation_id) {
                            loadedQuickSummaryForDoc = docId;
                            loadConversation(activeConversationId, activeChatTitle.innerText);
                        }
                    }
                } else if (doc.status === 'error') {
                    clearInterval(interval);
                    updateProgressStatus("Ready to chat ✓", false, "fa-circle-check");
                    setTimeout(() => {
                        fileUploadProgress.classList.add("hidden");
                    }, 1000);
                    alert("Document processing failed.");
                    removeAttachedFile();
                }
            } else {
                clearInterval(interval);
                fileUploadProgress.classList.add("hidden");
            }
        } catch (e) {
            clearInterval(interval);
            fileUploadProgress.classList.add("hidden");
        }
    }, 2000);
}

async function handleMismatchResolution(docId, action, detectedType = null) {
    mismatchModal.classList.add("hidden");
    
    if (action === 'cancel') {
        try {
            await fetch(`${BASE_URL}/api/documents/${docId}/confirm`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({ action: "cancel" })
            });
        } catch (err) {
            console.error("Cancel confirm failed:", err);
        }
        removeAttachedFile();
        return;
    }
    
    updateProgressStatus("Processing document...", true, "fa-spinner");
    fileUploadProgress.classList.remove("hidden");
    
    try {
        const response = await fetch(`${BASE_URL}/api/documents/${docId}/confirm`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ action: action, language: selectedLanguage })
        });
        
        if (response.ok) {
            if (action === 'change' && detectedType) {
                selectDocumentType(detectedType);
            }
            pollDocumentStatus(docId);
        } else {
            alert("Unable to process document resolution.");
            removeAttachedFile();
        }
    } catch (e) {
        console.error("Mismatch resolution failed:", e);
        removeAttachedFile();
    }
}

function appendEmptyAssistantMessageContainer() {
    const row = document.createElement("div");
    row.className = "message-row assistant-row";
    
    row.innerHTML = `
        <div class="message-cell">
            <div class="message-avatar"><i class="fa-solid fa-scale-balanced"></i></div>
            <div class="message-content">
                <div class="message-bubble">
                    <div class="message-bubble-text"></div>
                    <div class="message-sources hidden">
                        <div class="sources-title">Sources</div>
                        <div class="sources-list"></div>
                    </div>
                </div>
            </div>
        </div>
    `;
    messagesContainer.appendChild(row);
    return row;
}

function renderCitations(sources, sourcesTitle, sourcesList) {
    if (!sources || sources.length === 0) return;
    
    sourcesList.innerHTML = "";
    const tags = sources.map(s => {
        if (s.url === "#") {
            return `
                <span class="source-tag" style="cursor: default;" title="${escapeHTML(s.title)}">
                    <i class="fa-solid fa-file-invoice"></i> ${escapeHTML(s.title)}
                </span>
            `;
        }
        return `
            <a href="${s.url}" target="_blank" class="source-tag" title="${escapeHTML(s.title)}">
                <i class="fa-solid fa-link"></i> ${escapeHTML(s.title)}
            </a>
        `;
    }).join("");
    
    sourcesList.innerHTML = tags;
    sourcesTitle.classList.remove("hidden");
}
