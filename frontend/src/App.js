import React, { useState, useRef, useEffect, useCallback } from "react";
import { SunIcon, MoonIcon, PaperAirplaneIcon, StopIcon, PlusIcon, SparklesIcon, UserIcon } from "@heroicons/react/24/solid";

function App() {
  const [message, setMessage] = useState("");

  const [chatLog, setChatLog] = useState(() => {
    try {
      const savedChat = localStorage.getItem("chatLog");
      if (savedChat) {
        return JSON.parse(savedChat).map(msg => ({
          ...msg,
          timestamp: new Date(msg.timestamp)
        }));
      }
      return [];
    } catch (error) {
      console.error("Failed to parse chatLog from localStorage:", error);
      return [];
    }
  });
  const [loading, setLoading] = useState(false);
  const [botTypingText, setBotTypingText] = useState("");
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem("darkMode");
    return saved ? JSON.parse(saved) : true;
  });

  const [isAuthReady] = useState(true);
  const [selectedFile, setSelectedFile] = useState(null);

  // --- User Memory ---
  const [userMemory, setUserMemory] = useState(() => {
    try {
      const savedMemory = localStorage.getItem("userMemory");
      return savedMemory ? JSON.parse(savedMemory) : {};
    } catch (error) {
      console.error("Failed to parse userMemory from localStorage:", error);
      return {};
    }
  });

  // --- YOUR NAME HERE ---
  const creatorName = "Mark Dennis V. Manangan";

  const chatBoxRef = useRef(null);
  const abortControllerRef = useRef(null);
  const typingIntervalRef = useRef(null);
  const botReplyAddedRef = useRef(false);
  const fileInputRef = useRef(null);

  const isScrolledUpRef = useRef(false);

  useEffect(() => {
    localStorage.setItem("darkMode", JSON.stringify(darkMode));
    if (darkMode) {
      document.body.classList.add("dark-mode");
      document.body.classList.remove("light-mode");
    } else {
      document.body.classList.add("light-mode");
      document.body.classList.remove("dark-mode");
    }
  }, [darkMode]);

  // Save chatLog and userMemory to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem("chatLog", JSON.stringify(chatLog));
  }, [chatLog]);

  useEffect(() => {
    localStorage.setItem("userMemory", JSON.stringify(userMemory));
  }, [userMemory]);

  // Modified useEffect for smart scrolling
  useEffect(() => {
    const chatBox = chatBoxRef.current;
    if (chatBox) {
      const atBottom = chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight < 100;
      if (!isScrolledUpRef.current || atBottom) {
        chatBox.scrollTop = chatBox.scrollHeight;
      }
    }
  }, [chatLog, loading, botTypingText]);

  // useEffect to attach scroll listener
  useEffect(() => {
    const chatBox = chatBoxRef.current;
    if (chatBox) {
      const handleScroll = () => {
        const atBottom = chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight < 100;
        isScrolledUpRef.current = !atBottom;
      };

      chatBox.addEventListener('scroll', handleScroll);
      return () => {
        chatBox.removeEventListener('scroll', handleScroll);
      };
    }
  }, []);

  // --- UI/UX Enhancement: Typing Animation logic refined ---
  const typeEffect = useCallback((fullText) => {
    return new Promise((resolve) => {
      const words = fullText.split(' ');
      let wordIndex = 0;
      setBotTypingText("");
      if (typingIntervalRef.current) {
        clearInterval(typingIntervalRef.current);
      }
      typingIntervalRef.current = setInterval(() => {
        if (!abortControllerRef.current || !abortControllerRef.current.signal.aborted) {
            setBotTypingText((prev) => {
                if (wordIndex < words.length) {
                    const newText = prev + (wordIndex > 0 ? ' ' : '') + words[wordIndex];
                    wordIndex++;
                    return newText;
                } else {
                    clearInterval(typingIntervalRef.current);
                    typingIntervalRef.current = null;
                    if (!botReplyAddedRef.current) {
                        setChatLog((prevLog) => [...prevLog, { sender: "bot", text: fullText, timestamp: new Date() }]);
                        botReplyAddedRef.current = true;
                    }
                    resolve();
                    return prev;
                }
            });
        } else {
            clearInterval(typingIntervalRef.current);
            typingIntervalRef.current = null;
            resolve();
        }
      }, 70);
    });
  }, []);

  const stopTyping = useCallback(() => {
    if (typingIntervalRef.current) {
      clearInterval(typingIntervalRef.current);
      typingIntervalRef.current = null;
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    if (botTypingText.trim() !== "" && !botReplyAddedRef.current) {
      setChatLog((prev) => [...prev, { sender: "bot", text: botTypingText, timestamp: new Date() }]);
      botReplyAddedRef.current = true;
    }

    setLoading(false);
    setBotTypingText("");
    botReplyAddedRef.current = false;
  }, [botTypingText]);

  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      setSelectedFile(file);
      if (!message.trim()) {
        setMessage("");
      }
    }
  };

  const removeSelectedFile = () => {
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // API base (points to your Flask backend). Set REACT_APP_API_BASE_URL in .env if needed.
  const API_BASE = process.env.REACT_APP_API_BASE_URL || "";

  const sendMessage = useCallback(async (predefinedMessage = null) => {
    const messageToSend = predefinedMessage !== null ? predefinedMessage : message.trim();

    if ((!messageToSend && !selectedFile) || loading) {
      return;
    }

    let displayMessage = messageToSend;
    if (selectedFile) {
        displayMessage = messageToSend ? `${messageToSend} (File: ${selectedFile.name})` : `File: ${selectedFile.name}`;
    }

    setChatLog((prev) => [...prev, { sender: "user", text: displayMessage, timestamp: new Date() }]);

    setLoading(true);
    setBotTypingText("");
    setMessage("");
    setSelectedFile(null);
    if (fileInputRef.current) {
        fileInputRef.current.value = '';
    }

    botReplyAddedRef.current = false;
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    try {
      const lowerCaseMessage = messageToSend.toLowerCase();

      const creatorQuestions = [
        "who created you", "who made you", "who is your creator", "who make this",
        "who built you", "who designed you", "who named you",
        "your creator", "your name giver", "who created this chatbot",
        "who made this chatbot", "creator of this chatbot",
        "who built this webapp", "who developed this webapp",
        "this webapp created by", "who created this ai", "who made this ai",
      ];

      const isCreatorQuestion = creatorQuestions.some(phrase => lowerCaseMessage.includes(phrase));

      if (isCreatorQuestion) {
        const creatorReply = `I was created and named by ${creatorName}!`;
        await typeEffect(creatorReply);
        setLoading(false);
        setBotTypingText("");
        botReplyAddedRef.current = true;
        return;
      }

      const markIdentityQuestions = [
        "who is mark", "is mark your creator", "did mark create you",
        "tell me about mark", "who is manangan", "is manangan your developer",
        "who developed you mark", "who designed you mark", "mark developer", "mark creator",
        "who is mark dennis manangan", "about mark dennis v. manangan"
      ].map(phrase => phrase.toLowerCase());

      const isMarkIdentityQuestion = markIdentityQuestions.some(phrase => lowerCaseMessage.includes(phrase));

      if (isMarkIdentityQuestion) {
        const markReply = `${creatorName} is the brilliant mind who created and named me, Chatbot AI!`;
        await typeEffect(markReply);
        setLoading(false);
        setBotTypingText("");
        botReplyAddedRef.current = true;
        return;
      }

      const currentInputParts = [];
      if (messageToSend) {
        currentInputParts.push({ text: messageToSend });
      }
      if (selectedFile) {
        setBotTypingText("Processing file...");
        const reader = new FileReader();
        const fileBase64 = await new Promise((resolve, reject) => {
          reader.onloadend = () => resolve(reader.result.split(',')[1]);
          reader.onerror = reject;
          reader.readAsDataURL(selectedFile);
        });

        currentInputParts.push({
          inlineData: {
            mimeType: selectedFile.type,
            data: fileBase64,
          },
        });
      }

      const chatHistoryForAPI = [];

      let systemInstruction = "You are Chatbot, a helpful and friendly AI assistant. Keep your responses concise and informative.";

      if (Object.keys(userMemory).length > 0) {
        systemInstruction += `\nUser's persistent memory: ${JSON.stringify(userMemory)}.`;
      }

      let firstMessageProcessed = false;

      chatLog.forEach(msg => {
          if (msg.sender === "user") {
              if (!firstMessageProcessed) {
                  chatHistoryForAPI.push({
                      role: "user",
                      parts: [{ text: `${systemInstruction}\n${msg.text}` }]
                  });
                  firstMessageProcessed = true;
              } else {
                  chatHistoryForAPI.push({
                      role: "user",
                      parts: [{ text: msg.text }]
                  });
              }
          } else if (msg.sender === "bot") {
              chatHistoryForAPI.push({
                  role: "model",
                  parts: [{ text: msg.text }]
              });
          }
      });

      if (!firstMessageProcessed) {
          const firstUserMessageParts = [];
          if (messageToSend) {
              firstUserMessageParts.push({ text: `${systemInstruction}\n${messageToSend}` });
          } else {
              firstUserMessageParts.push({ text: systemInstruction });
          }

          if (selectedFile) {
              const reader = new FileReader();
              const fileBase64 = await new Promise((resolve, reject) => {
                  reader.onloadend = () => resolve(reader.result.split(',')[1]);
                  reader.onerror = reject;
                  reader.readAsDataURL(selectedFile);
              });
              firstUserMessageParts.push({
                  inlineData: {
                      mimeType: selectedFile.type,
                      data: fileBase64,
                  },
              });
          }
          chatHistoryForAPI.push({ role: "user", parts: firstUserMessageParts });

      } else {
          chatHistoryForAPI.push({ role: "user", parts: currentInputParts });
      }

      const payload = {
        contents: chatHistoryForAPI,
        generationConfig: {
            temperature: 0.7,
            topK: 40,
            topP: 0.95,
        },
      };

      // --- NEW: send request to your Flask backend (no API key in frontend) ---
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(`API Error: ${response.status} - ${errorData.message || response.statusText}`);
      }

      const result = await response.json();

      // Try multiple possible response shapes coming from backend
      const replyText = result.reply || result.text || (result.candidates && result.candidates[0]?.content?.parts?.[0]?.text) || result.message || result.answer || "Sorry, I couldn't get a response from Chatbot.";

      if (!signal.aborted) {
        await typeEffect(replyText);
      } else {
        setBotTypingText("");
      }

      const nameMatch = messageToSend.match(/(?:my name is|I'm)\s+([A-Z][a-z]+)/i);
      if (nameMatch) {
        const userName = nameMatch[1];
        setUserMemory(prev => ({ ...prev, name: userName }));
      }

    } catch (error) {
      if (error.name !== "AbortError") {
        let errorMsg = `Error connecting to Chatbot: ${error.message || "Please check your network."}`;
        if (error.message && error.message.includes("API Error")) {
            errorMsg = `Chatbot encountered an issue: ${error.message}. Please try again later.`;
        }
        setChatLog((prev) => [...prev, { sender: "bot", text: errorMsg, timestamp: new Date() }]);
      }
    } finally {
      if (!botReplyAddedRef.current && botTypingText.trim() !== "") {
          setChatLog((prev) => [...prev, { sender: "bot", text: botTypingText, timestamp: new Date() }]);
      }
      setLoading(false);
      setBotTypingText("");
      abortControllerRef.current = null;
      typingIntervalRef.current = null;
      botReplyAddedRef.current = false;
    }
  }, [message, loading, chatLog, typeEffect, selectedFile, botTypingText, userMemory, creatorName]);

  return (
    <div
      className={`h-screen flex flex-col items-center p-4 pb-0 relative font-inter transition-all duration-500 ease-in-out cursor-default
        ${darkMode
          ? "bg-black text-gray-100"
          : "bg-gradient-to-br from-blue-50 to-purple-100 text-gray-900"
        }`}
    >
      {/* Header with Separator Line */}
      <div className={`w-full max-w-3xl mb-4 sm:mb-6 pb-4 border-b ${
        darkMode ? "border-gray-700" : "border-gray-300"
      }`}>
        <div className="flex justify-between items-center">
          {/* Title */}
          <h1 className="text-3xl sm:text-4xl font-extrabold drop-shadow-lg select-none text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-400">
            Chatbot
          </h1>

          {/* Theme Toggle Button */}
          <button
            onClick={() => setDarkMode((prev) => !prev)}
            aria-label="Toggle dark mode"
            className={`relative w-16 h-8 rounded-full p-1 transition-all duration-500 ease-in-out transform hover:scale-105 cursor-pointer shadow-lg ${
              darkMode 
                ? "bg-gradient-to-r from-purple-600 to-indigo-600" 
                : "bg-gradient-to-r from-blue-400 to-purple-400"
            }`}>
            {/* Toggle Knob */}
            <div
              className={`absolute top-1 w-6 h-6 rounded-full bg-white shadow-md transform transition-all duration-500 ease-in-out ${
                darkMode ? "translate-x-8" : "translate-x-0"
              }`}>
              {/* Icons inside toggle */}
              <div className="absolute inset-0 flex items-center justify-center">
                {darkMode ? (
                  <MoonIcon className="h-3 w-3 text-indigo-800" />
                ) : (
                  <SunIcon className="h-3 w-3 text-yellow-500" />
                )}
              </div>
            </div>
            
            {/* Background Icons */}
            <div className="flex justify-between items-center px-1 h-full">
              <SunIcon className={`h-4 w-4 transition-all duration-500 ${
                darkMode ? "text-gray-400 opacity-50" : "text-yellow-300"
              }`} />
              <MoonIcon className={`h-4 w-4 transition-all duration-500 ${
                darkMode ? "text-white" : "text-gray-400 opacity-50"
              }`} />
            </div>
          </button>
        </div>
      </div>

      {/* Chat Box */}
      <div
        ref={chatBoxRef}
        className={`w-full max-w-3xl flex-1 overflow-y-auto rounded-3xl shadow-inset-lg p-4 sm:p-6 mb-4 sm:mb-6 scrollbar-hide
          ${darkMode ? "bg-gray-900" : "bg-white/80"}
          backdrop-blur-xl space-y-4 sm:space-y-5 border border-transparent
          ${darkMode ? "border-gray-700" : "border-gray-200"}
          transition-all duration-500 ease-in-out`}
        aria-live="polite"
        tabIndex={0}
      >
        {chatLog.length === 0 && !loading && (
          <div className="text-center text-gray-400 italic mt-10 sm:mt-20 text-sm sm:text-base">
            Start a conversation with Chatbot
            {userMemory.name && (
              <p className="mt-2">Welcome back, {userMemory.name}!</p>
            )}
          </div>
        )}
        {chatLog.map((msg, index) => (
          <div
            key={index}
            className={`flex flex-col max-w-[90%] sm:max-w-[75%] text-sm sm:text-base ${
              msg.sender === "user" ? "ml-auto items-end" : "mr-auto items-start"
            }`}>
            <span className={`text-xs font-medium mb-1 opacity-70 flex items-center ${
              msg.sender === "user"
                ? darkMode ? "text-blue-300" : "text-blue-600"
                : darkMode ? "text-purple-300" : "text-purple-600"
            }`}>
              {msg.sender === "user" ? <UserIcon className="h-3 w-3 mr-1" /> : <SparklesIcon className="h-3 w-3 mr-1" />}
              {msg.sender === "user" ? (userMemory.name || "You") : "Chatbot"}
              <span className="ml-2 text-xs opacity-50">
                {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </span>
            <div
              className={`px-4 py-2 sm:px-5 sm:py-3 rounded-2xl break-words whitespace-pre-wrap shadow-md transform transition-all duration-300 ease-out-back ${
                msg.sender === "user"
                  ? "bg-blue-600 text-white"
                  : darkMode
                    ? "bg-gray-800 text-gray-50"
                    : "bg-gray-100 text-gray-800"
              }`}>
              {msg.text}
            </div>
          </div>
        ))}

        {/* Loading and Typing Animation */}
        {loading && botTypingText && (
          <div className="flex flex-col max-w-[90%] sm:max-w-[75%] mr-auto items-start text-sm sm:text-base">
            <span className={`text-xs font-medium mb-1 opacity-70 flex items-center ${darkMode ? "text-purple-300" : "text-purple-600"}`}>
              <SparklesIcon className="h-3 w-3 mr-1" />Chatbot
            </span>
            <div
              className={`px-4 py-2 sm:px-5 sm:py-3 rounded-2xl italic break-words whitespace-pre-wrap shadow-md ${
                darkMode ? "bg-gray-800 text-gray-50" : "bg-gray-100 text-gray-800"
              }`}>
              {botTypingText}
              <span className="blinking-cursor text-purple-400">|</span>
            </div>
          </div>
        )}

        {loading && !botTypingText && (
          <div className="flex items-center justify-start text-purple-400 text-xs sm:text-sm animate-pulse ml-2">
            <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce-dot animation-delay-0"></div>
            <div className="w-2 h-2 bg-purple-400 rounded-full ml-1 animate-bounce-dot animation-delay-100"></div>
            <div className="w-2 h-2 bg-purple-400 rounded-full ml-1 animate-bounce-dot animation-delay-200"></div>
            <span className="ml-2">Thinking...</span>
          </div>
        )}
      </div>

      {/* Input Area - ChatGPT Style */}
      <div className={`w-full max-w-3xl mb-4`}>
        {selectedFile && (
          <div className={`flex items-center justify-center space-x-2 p-2 rounded-lg text-xs sm:text-sm mb-2
            ${darkMode ? "bg-gray-800 text-gray-200" : "bg-gray-200 text-gray-700"}`}>
            <span>
              {selectedFile.type.startsWith('image/') ? 'Image' : 'File'}: {selectedFile.name}
            </span>
            <button onClick={removeSelectedFile} className="text-red-500 hover:text-red-700">
              &times;
            </button>
          </div>
        )}
        
        <div className={`flex items-center gap-2 p-2 rounded-xl shadow-xl backdrop-blur-lg
          ${darkMode ? "bg-gray-800 border border-gray-700" : "bg-white border border-gray-300"}
          transition-all duration-500 ease-in-out`}>

          {/* Hidden file input */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            style={{ display: 'none' }}
            accept="image/*, application/pdf, .txt, audio/*, video/*"
          />

          <input
            type="text"
            value={message}
            placeholder={"Type your message to Chatbot..."}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                if (!loading && (message.trim() || selectedFile)) {
                  sendMessage();
                }
              }
            }}
            disabled={loading || !isAuthReady}
            aria-label="Type your message"
            className={`flex-1 px-4 py-3 rounded-xl border-none focus:outline-none focus:ring-0 placeholder-gray-400 text-sm sm:text-base
              ${darkMode
                ? "bg-gray-700 text-gray-100 caret-purple-400 focus:bg-gray-700"
                : "bg-white text-gray-900 caret-blue-600 focus:bg-white"}
              disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300`}
          />

          {/* Plus Icon Button */}
          <button
            onClick={() => fileInputRef.current.click()}
            disabled={loading || !isAuthReady}
            aria-label="Attach file"
            className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300 transform active:scale-95 shadow-lg
              ${darkMode
                ? "bg-gray-700 text-gray-300 hover:bg-gray-600"
                : "bg-gray-200 text-gray-700 hover:bg-gray-300"
              }
              disabled:opacity-40 disabled:cursor-not-allowed`}>
            <PlusIcon className="h-5 w-5" />
          </button>
          
          <button
            onClick={loading ? stopTyping : () => sendMessage()}
            disabled={(!message.trim() && !selectedFile && !loading) || !isAuthReady}
            aria-label={loading ? "Stop generating response" : "Send message"}
            className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300 transform active:scale-95 shadow-lg
              ${loading
                ? darkMode
                  ? "bg-red-600 text-white hover:bg-red-500 animate-pulse"
                  : "bg-red-500 text-white hover:bg-red-400"
                : darkMode
                ? "bg-gradient-to-r from-purple-600 to-indigo-600 text-white hover:from-purple-500 hover:to-indigo-500"
                : "bg-gradient-to-r from-blue-500 to-purple-500 text-white hover:from-blue-400 hover:to-purple-400"}
              disabled:opacity-40 disabled:cursor-not-allowed`}>
            {loading ? (
              <StopIcon className="h-5 w-5" />
            ) : (
              <PaperAirplaneIcon className="h-5 w-5" />
            )}
          </button>
        </div>
      </div>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
        body { font-family: 'Inter', sans-serif; margin: 0; padding: 0; }

        /* General scrollbar styling */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }

        /* Track */
        ::-webkit-scrollbar-track {
            background: transparent;
        }

        /* Handle */
        ::-webkit-scrollbar-thumb {
            background: rgba(156, 163, 175, 0.5);
            border-radius: 10px;
        }

        /* Handle on hover */
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(156, 163, 175, 0.7);
        }

        /* Dark mode scrollbar */
        body.dark-mode ::-webkit-scrollbar-thumb {
            background: rgba(75, 85, 99, 0.5);
        }
        body.dark-mode ::-webkit-scrollbar-thumb:hover {
            background: rgba(75, 85, 99, 0.7);
        }

        /* Hide scrollbar for IE, Edge and Firefox */
        .scrollbar-hide {
            -ms-overflow-style: none;
            scrollbar-width: none;
        }

        .blinking-cursor {
          font-weight: 100;
          font-size: 1.2em;
          color: #a855f7;
          animation: blink 1s infinite;
        }
        @keyframes blink {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }

        .shadow-inset-lg {
            box-shadow: inset 0 0 15px rgba(0,0,0,0.2);
        }

        .animate-pulse-light {
          animation: pulse-light 3s infinite ease-in-out;
        }
        @keyframes pulse-light {
          0%, 100% { opacity: 1; text-shadow: 0 0 5px rgba(96, 165, 250, 0.7); }
          50% { opacity: 0.8; text-shadow: 0 0 20px rgba(168, 85, 247, 0.9); }
        }

        .animate-bounce-dot {
            animation: bounce-dot 1s infinite cubic-bezier(0.68, -0.55, 0.265, 1.55);
        }
        .animation-delay-0 { animation-delay: 0s; }
        .animation-delay-100 { animation-delay: 0.1s; }
        .animation-delay-200 { animation-delay: 0.2s; }

        @keyframes bounce-dot {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-5px); }
        }
      `}</style>
    </div>
  );
}

export default App;
