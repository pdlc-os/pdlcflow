import { useParams } from 'react-router-dom';

import { ChatPanel } from '@/components/ChatPanel';
import { MemoryFileViewer } from '@/components/MemoryFileViewer';
import { SketchSocraticToggle } from '@/components/SketchSocraticToggle';

export function ProjectView() {
  const { id } = useParams<{ id: string }>();
  return (
    <div className="grid grid-cols-[1fr_280px] gap-4">
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold tracking-tight">Project {id}</h2>
          <SketchSocraticToggle />
        </div>
        <ChatPanel />
      </div>
      <aside>
        <MemoryFileViewer />
      </aside>
    </div>
  );
}
