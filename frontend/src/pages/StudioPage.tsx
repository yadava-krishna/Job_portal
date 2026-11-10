import { useParams } from "react-router-dom";
import { EmptyState } from "@/components/app/common";
import { StudioEditor } from "@/features/studio/StudioEditor";
import { VersionList } from "@/features/studio/VersionList";

/** Resume Studio: /studio lists versions, /studio/:id opens the editor with a live PDF preview. */
export function StudioPage() {
  const { id } = useParams<{ id?: string }>();
  if (id == null) return <VersionList />;
  const n = Number(id);
  if (!Number.isInteger(n) || n <= 0) return <EmptyState title="Resume not found">Check the link, or open a resume from Resume Studio.</EmptyState>;
  // key: switching versions remounts the editor so pending edits of the previous one are flushed, not mixed.
  return <StudioEditor key={n} id={n} />;
}
