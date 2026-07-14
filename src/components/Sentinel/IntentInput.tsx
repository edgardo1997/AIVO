import { useRef, useState } from "react";

interface IntentInputProps {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function IntentInput({ onSend, disabled, placeholder = "What do you want to do?" }: IntentInputProps) {
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSend = () => {
    const trimmed = text.trim();
    if (trimmed && !disabled) {
      onSend(trimmed);
      setText("");
    }
  };

  return (
    <div className="intent-input-area">
      <input
        ref={inputRef}
        className="chat-input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleSend()}
        placeholder={placeholder}
        disabled={disabled}
        style={{ flex: 1 }}
      />
      <button className="btn btn-primary" onClick={handleSend} disabled={disabled || !text.trim()}>
        {disabled ? "Processing..." : "Go"}
      </button>
    </div>
  );
}
