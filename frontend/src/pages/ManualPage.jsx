import { useAppContext } from "../AppContext";

export default function ManualPage() {
  const { navigateTo } = useAppContext();

  return (
    <div className="page-content">
      <button className="page-back" onClick={() => navigateTo("capture")}>
        ← Go back
      </button>

      <h2>How to use SnapCapture</h2>

      <p>
        SnapCapture is a quick capture buffer for the ideas, tasks, and
        appointments that float through your day. It is not a permanent
        organizer — think of it as a notepad you empty regularly.
      </p>

      <h3>Capture anything</h3>
      <p>
        Drop in text, upload a file, or record audio. You can paste an email,
        drag in a screenshot, or speak a reminder into the microphone. Each
        input method works the same way: local processing runs first, then AI
        extracts the actionable items.
      </p>
      <p>
        For files, SnapCapture runs OCR locally on images and PDFs before
        deciding whether to send anything to an AI model. For audio, a local
        transcription converts your voice memo into text first. This keeps
        your data on-device as much as possible and avoids unnecessary API
        calls.
      </p>

      <h3>Choose your AI engine</h3>
      <p>
        By default, SnapCapture uses Gemini 2.5 Flash Lite for extraction. If you open
        Settings from the menu, you can switch to GPT-4o-mini instead.
        Advanced users can also bring their own API key — the key stays in
        your browser and is only sent to the AI provider you selected, never
        anywhere else.
      </p>

      <h3>Review what the AI found</h3>
      <p>
        After analysis, each extracted item appears as a card. The AI might
        find a single task or pull out six different appointments from one
        long message. You can edit the title, date, or description inline if
        the extraction needs a tweak. Save the ones you want to keep, reject
        the ones you don't.
      </p>

      <h3>The Dashboard</h3>
      <p>
        Saved items land in the Dashboard, where you can mark things done,
        add a quick note, or delete what you no longer need. Select multiple
        items to bulk-export or bulk-delete. Every item has a small menu for
        individual actions like editing or exporting just that one entry.
      </p>
      <p>
        The Dashboard is intentionally temporary. Items are automatically
        removed after one hour to keep the buffer light and encourage you to
        export what matters into your calendar or task manager quickly.
      </p>

      <h3>Export and move on</h3>
      <p>
        Tasks can be exported as CSV for easy import into Excel, Todoist,
        Notion, or any task manager that accepts spreadsheet files. Tasks can
        also be exported as .ics (VTODO) for Apple Reminders and some Outlook
        versions. Events always export as standard .ics calendar files that open
        directly in Google Calendar, Outlook, or Apple Calendar. Once you have
        exported what you need, clear the buffer. SnapCapture is designed for
        temporary holding, not long-term storage.
      </p>

      <h3>A few tips</h3>
      <p>
        Press Ctrl + Enter (or Cmd + Enter on a Mac) to trigger analysis
        without reaching for the mouse. The character limit for raw text is
        1000 characters — for longer content, upload it as a file instead.
        If you are using your own API key, SnapCapture skips the built-in
        quota tracking and lets you manage your own usage.
      </p>
    </div>
  );
}
