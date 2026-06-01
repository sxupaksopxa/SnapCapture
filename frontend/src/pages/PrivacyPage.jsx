import { useAppContext } from "../AppContext";

export default function PrivacyPage() {
  const { navigateTo } = useAppContext();

  return (
    <div className="page-content">
      <button className="page-back" onClick={() => navigateTo("capture")}>
        ← Go back
      </button>

      <h2>Privacy</h2>

      <p>
        SnapCapture is built around a simple idea: process your data locally
        whenever possible, send as little as possible to external services,
        and never keep anything longer than necessary.
      </p>

      <h3>Local-first processing</h3>
      <p>
        When you upload an image or PDF, the text is extracted on the server
        using local OCR before any AI model sees it. Audio recordings are
        transcribed locally as well. The AI only receives the extracted text,
        not the original file bytes. If the local OCR finds nothing, the
        image may be sent to the AI's vision model as a fallback — but that
        is the exception, not the rule.
      </p>

      <h3>What the AI sees</h3>
      <p>
        The AI provider you choose — Gemini 2.5 Flash Lite or GPT-4o-mini — receives only
        the text extracted from your input. It does not receive your
        uploaded files, your audio recordings, or any metadata beyond what
        is needed to identify tasks and events. SnapCapture does not use
        AI providers for analytics, profiling, or any purpose other than
        structured extraction.
      </p>

      <h3>Your API key, your control</h3>
      <p>
        If you bring your own API key in Settings, it is stored only in your
        browser's localStorage. It is sent only to the AI endpoints that need
        it, and never to any other part of the SnapCapture backend. The
        server does not log, store, or otherwise handle your key.
      </p>

      <h3>Session isolation</h3>
      <p>
        Your data is tied to a session identifier derived from your device.
        There are no user accounts, no passwords, and no way for one session
        to access another's data. This also means there is no password
        recovery — your data lives only in your current browser session.
      </p>

      <h3>Temporary by design</h3>
      <p>
        SnapCapture is a capture buffer, not a filing cabinet. Extracted
        items are intended to be exported or deleted within a short time.
        Uploaded files, recordings, and extracted items are all temporary
        by design. The server does not back up your data or retain it
        beyond its operational purpose.
      </p>

      <h3>No tracking</h3>
      <p>
        There are no analytics cookies, no third-party trackers, and no
        behavioral profiling. The only data stored is the content you
        explicitly capture and save to the Dashboard.
      </p>

      <h3>Your control</h3>
      <p>
        You can delete any item at any time, individually or in bulk. The
        Dashboard has a select-all option for quick cleanup. If you want to
        wipe everything, just select all and delete.
      </p>
    </div>
  );
}
