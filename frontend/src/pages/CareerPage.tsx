import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/app/common";
import { GapsTab } from "@/features/career/GapsTab";
import { LearningTab } from "@/features/career/LearningTab";
import { SkillsTab } from "@/features/career/SkillsTab";

const TABS = ["gaps", "skills", "learning"];

export function CareerPage() {
  // Deep links such as #/career?tab=learning.
  const [params, setParams] = useSearchParams();
  const tab = TABS.includes(params.get("tab") ?? "") ? params.get("tab")! : "gaps";
  const [gapId, setGapId] = useState<number | null>(null);
  const setTab = (t: string) => setParams((p) => { const next = new URLSearchParams(p); next.set("tab", t); return next; }, { replace: true });

  return (
    <>
      <PageHeader title="Career growth" description="The skills your target jobs ask for, the evidence you have, and ways to close the gaps." />
      <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
        <div className="overflow-x-auto pb-1">
          <TabsList>
            <TabsTrigger value="gaps">Gaps</TabsTrigger>
            <TabsTrigger value="skills">Skills & evidence</TabsTrigger>
            <TabsTrigger value="learning">Learning</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="gaps" className="pt-4"><GapsTab onLearn={(id) => { setGapId(id); setTab("learning"); }} /></TabsContent>
        <TabsContent value="skills" className="pt-4"><SkillsTab /></TabsContent>
        <TabsContent value="learning" className="pt-4"><LearningTab gapId={gapId} onSelectGap={setGapId} /></TabsContent>
      </Tabs>
    </>
  );
}
