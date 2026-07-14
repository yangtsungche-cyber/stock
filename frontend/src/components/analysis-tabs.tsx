"use client";

import { DecisionSummaryPanel } from "@/components/decision-summary-panel";
import { GranvillePanel } from "@/components/granville-panel";
import { IndicatorLayersPanel } from "@/components/indicator-layers-panel";
import {
  AnnouncementsPanel,
  ChipsSignalPanel,
  InstitutionalPanel,
  MarginPanel,
} from "@/components/margin-institutional-panel";
import { PriceChartPanel } from "@/components/price-chart-panel";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WavePanel } from "@/components/wave-panel";

function ComingSoon({ label }: { label: string }) {
  return (
    <Card>
      <CardContent className="py-10 text-center text-muted-foreground">
        {label} 尚未串接，將於後續 Step 完成。
      </CardContent>
    </Card>
  );
}

export function AnalysisTabs({ symbol }: { symbol: string }) {
  return (
    <Tabs defaultValue="chart" className="w-full">
      <TabsList>
        <TabsTrigger value="chart">K線圖</TabsTrigger>
        <TabsTrigger value="layers">八層分析</TabsTrigger>
        <TabsTrigger value="decision">決策摘要</TabsTrigger>
        <TabsTrigger value="playbook">Investment Playbook</TabsTrigger>
      </TabsList>

      <TabsContent value="chart" className="mt-4">
        <Card>
          <CardContent className="pt-6">
            <PriceChartPanel symbol={symbol} />
          </CardContent>
        </Card>
      </TabsContent>

      <TabsContent value="layers" className="mt-4 space-y-3">
        <GranvillePanel symbol={symbol} />
        <WavePanel symbol={symbol} />
        <IndicatorLayersPanel symbol={symbol} />
        <ChipsSignalPanel symbol={symbol} />
        <MarginPanel symbol={symbol} />
        <InstitutionalPanel symbol={symbol} />
        <AnnouncementsPanel symbol={symbol} />
      </TabsContent>

      <TabsContent value="decision" className="mt-4">
        <DecisionSummaryPanel symbol={symbol} />
      </TabsContent>

      <TabsContent value="playbook" className="mt-4">
        <ComingSoon label="Investment Playbook" />
      </TabsContent>
    </Tabs>
  );
}
