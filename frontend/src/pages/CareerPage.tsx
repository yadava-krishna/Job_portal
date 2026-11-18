import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BadgeCheck, BookOpen, Target } from "lucide-react";
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
      <PageHeader eyebrow="Skills & learning" title={<>Glow-up <em>season</em>. Let's level up.</>}
                  description="The skills your target jobs keep asking for, the evidence you already have, and a short plan to close the gaps." />
      <Tabs value={tab} onValueChange={(v) => setTab(String(v))} className="gap-0">
        <div className="-mx-1 overflow-x-auto px-1 pb-1">
          <TabsList>
            <TabsTrigger value="gaps"><Target aria-hidden /> Gaps</TabsTrigger>
            <TabsTrigger value="skills"><BadgeCheck aria-hidden /> Skills & evidence</TabsTrigger>
            <TabsTrigger value="learning"><BookOpen aria-hidden /> Learning</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="gaps" className="pt-4"><GapsTab onLearn={(id) => { setGapId(id); setTab("learning"); }} /></TabsContent>
        <TabsContent value="skills" className="pt-4"><SkillsTab /></TabsContent>
        <TabsContent value="learning" className="pt-4"><LearningTab gapId={gapId} onSelectGap={setGapId} /></TabsContent>
      </Tabs>
    </>
  );
}
