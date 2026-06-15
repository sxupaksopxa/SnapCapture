import { useAppContext } from "../AppContext";

export default function AboutPage() {
  const { navigateTo } = useAppContext();

  return (
    <div className="page-content">
      <button className="page-back" onClick={() => navigateTo("capture")}>
        ← Go back
      </button>
      <h2>About SnapCapture</h2>
      <p>
        SnapCapture is a lightweight tool for quickly collecting tasks,
        reminders, appointments, and follow-ups.
      </p>
      <p>
        Paste text, upload a file, or record audio. SnapCapture extracts
        actionable items so they can be reviewed and exported to your calendar or organizer.
      </p>
      <p>
        It is designed as a temporary capture buffer — not a permanent storage system.
      </p>
      <h3>Technical Background</h3>
      <p>
        SnapCapture uses local OCR and audio transcription
        whenever possible to reduce API usage and improve privacy.
      </p>
      <p>
        Images and PDFs are processed locally with OCR before optional AI enhancement.
        Audio recordings use local transcription before AI extraction.
      </p>
      <p>
        AI extraction is used only when needed.
      </p>
      <p>
        SnapCapture supports multiple extraction engines such as Gemini 2.5 Flash Lite and GPT-4o-mini.
      </p>
      <p>
        Advanced users can optionally use <strong>BYOK</strong> (Bring Your Own Key)
        to connect their own AI provider and manage their own API usage limits.
      </p>

      <h3>Version</h3>
      <p>SnapCapture MVP v0.9</p>
      <p>Small practical tool for real everyday usage</p>

      <h3>Support & Feedback</h3>
      <p>Questions, bug reports, feature requests and general feedback are welcome.</p>
      <p>support@snapcapture.net</p>
    </div>
  );
}
