import { useState, useEffect, useRef, UIEvent } from 'react'

const SERVER_HTTP = 'http://127.0.0.1:8000/api/command'
const SERVER_WS = 'ws://127.0.0.1:8000/ws/feed'

export default function App() {
  const [status, setStatus] = useState<'idle' | 'thinking' | 'speaking' | 'error' | 'offline'>('offline')
  const [messages, setMessages] = useState<{ role: string; text: string; id: number }>([
    { role: 'system', text: 'System online. Awaiting commands...', id: Date.now() }
  ])
  const [input, setInput] = useState('')
  const [isAtBottom, setIsAtBottom] = useState(true)
  
  const scrollRef = useRef<HTMLDivElement>(null)

  // SmoothUI Rule: Only auto-scroll if the user is already at the bottom
  useEffect(() => {
    if (isAtBottom && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  const handleScroll = (e: UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget
    // Check if within 48px of the bottom
    setIsAtBottom(scrollHeight - scrollTop - clientHeight < 48)
  }

  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth'
      })
    }
  }

  useEffect(() => {
    let ws: WebSocket
    const connect = () => {
      ws = new WebSocket(SERVER_WS)
      ws.onopen = () => setStatus('idle')
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.event === 'speak') setStatus('speaking')
          if (data.event === 'idle') setStatus('idle')
        } catch (e) {
          console.error('WS Parse Error', e)
        }
      }
      ws.onclose = () => {
        setStatus('offline')
        setTimeout(connect, 3000)
      }
    }
    connect()
    return () => ws?.close()
  }, [])

  const sendCommand = async (e: React.FormEvent) => {
    e.preventDefault()
    const query = input.trim()
    if (!query) return

    setInput('')
    setStatus('thinking')
    setMessages((prev) => [...prev, { role: 'user', text: query, id: Date.now() }])

    // Force scroll to bottom on user input
    setTimeout(scrollToBottom, 50)

    try {
      const res = await fetch(SERVER_HTTP, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: query })
      })
      if (res.ok) {
        const data = await res.json()
        setMessages((prev) => [...prev, { role: 'ava', text: data.reply || 'Action completed.', id: Date.now() }])
      } else {
        setMessages((prev) => [...prev, { role: 'system', text: `Server Error: ${res.status}`, id: Date.now() }])
      }
      setStatus('idle')
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'system', text: `Connection Error: ${err}`, id: Date.now() }])
      setStatus('error')
    }
  }

  const getOrbStyle = () => {
    let colors = 'from-[#e83e8c] via-[#3b82f6] to-[#c084fc]'
    let animation = 'animate-[spin_4s_linear_infinite]'
    let scale = 'scale-100'

    if (status === 'thinking') {
      colors = 'from-[#bfdbfe] via-[#fbcfe8] to-[#e0e7ff]'
      animation = 'animate-[spin_1.5s_linear_infinite]'
    } else if (status === 'speaking') {
      colors = 'from-[#06b6d4] via-[#f472b6] to-[#a855f7]'
      animation = 'animate-[spin_2s_linear_infinite]'
      scale = 'animate-[pulse_1s_ease-in-out_infinite]'
    } else if (status === 'error' || status === 'offline') {
      colors = 'from-[#94a3b8] via-[#a8a29e] to-[#64748b]'
    }

    return { colors, animation, scale }
  }

  const orb = getOrbStyle()

  return (
    <div 
      className="flex flex-col h-screen bg-[#fafafa]/95 border border-[#e4e4e7] rounded-xl overflow-hidden text-sm relative shadow-2xl"
      style={{ WebkitAppRegion: 'drag' } as any}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 bg-white/50 border-b border-[#e4e4e7]">
        <h1 className="text-[#52525b] font-bold tracking-widest text-xs">PROJECT ARC // AVA</h1>
        
        <div className="flex items-center gap-3">
          <div className={`relative w-5 h-5 rounded-full flex items-center justify-center overflow-hidden ${orb.scale}`}>
            <div className={`absolute inset-0 bg-gradient-conic ${orb.colors} ${orb.animation}`} />
            <div className="absolute inset-0 bg-radial-gradient from-white/60 to-transparent" />
          </div>
          <span className="text-[#52525b] font-bold tracking-wider text-[10px] uppercase">
            {status}
          </span>
        </div>
      </div>

      {/* Chat History */}
      <div 
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-5 space-y-6 relative"
        style={{ WebkitAppRegion: 'no-drag' } as any}
      >
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'user' ? (
              // SmoothUI User Bubble
              <div className="bg-[#18181b] text-[#f4f4f5] px-5 py-3 rounded-[24px] max-w-[80%] shadow-sm leading-relaxed text-[15px]">
                {msg.text}
              </div>
            ) : msg.role === 'system' ? (
              <div className="text-[#a1a1aa] italic text-xs px-2">
                {msg.text}
              </div>
            ) : (
              // SmoothUI AI Bubble
              <div className="flex gap-3 max-w-[90%]">
                <div className="w-6 h-6 rounded-full bg-gradient-to-br from-[#06b6d4] via-[#a855f7] to-[#ec4899] flex-shrink-0 mt-1 shadow-sm" />
                <div className="bg-[#f4f4f5] text-[#27272a] px-5 py-4 rounded-[24px] shadow-sm leading-relaxed text-[15px]">
                  {msg.text}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Floating Jump-to-Latest Pill */}
      {!isAtBottom && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-20 left-1/2 -translate-x-1/2 bg-white text-[#27272a] px-4 py-1.5 rounded-full shadow-md border border-[#e4e4e7] text-xs font-semibold flex items-center gap-2 hover:bg-gray-50 transition-colors z-10"
          style={{ WebkitAppRegion: 'no-drag' } as any}
        >
          <span>↓</span> Jump to latest
        </button>
      )}

      {/* Input Form */}
      <form 
        onSubmit={sendCommand} 
        className="p-4 bg-white/50 border-t border-[#e4e4e7]"
        style={{ WebkitAppRegion: 'no-drag' } as any}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask Ava or give an instruction..."
          className="w-full bg-white text-[#27272a] border border-[#e4e4e7] rounded-xl px-4 py-3 focus:outline-none focus:border-[#a855f7] focus:ring-1 focus:ring-[#a855f7] transition-all placeholder-[#a1a1aa] shadow-sm"
        />
      </form>
    </div>
  )
}
