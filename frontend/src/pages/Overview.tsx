import { useState } from "react";
import { EventFeed } from "../components/EventFeed";
import { LiveChart } from "../components/LiveChart";
import { OrganCard } from "../components/OrganCard";
import { RecentChart } from "../components/RecentChart";
import { StatePanel } from "../components/StatePanel";
import { VitalsPanel } from "../components/VitalsPanel";
import { WellnessPanel } from "../components/WellnessPanel";
import type { LiveTwin } from "../hooks/useLiveTwin";
import { TwinScene } from "../twin3d/TwinScene";

export function Overview({ twin, recorded = false }: { twin: LiveTwin; recorded?: boolean }) {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <div className="overview">
      <div className="overview__state">
        <StatePanel state={twin.state} />
        <WellnessPanel state={twin.state} />
      </div>
      <div className="overview__twin">
        <TwinScene payload={twin.state} selected={selected} onSelect={setSelected} />
        {selected ? (
          <OrganCard name={selected} state={twin.state} onClose={() => setSelected(null)} />
        ) : (
          <p className="twin-caption">
            Real anatomy from scan data. The heart beats at the live heart rate, arteries pulse with it, the lungs and
            diaphragm move at the breathing rate, muscles glow with activity, and the body lies down during sleep.
            Structures with no sensor data stay still. Click any organ for details; drag to rotate.
          </p>
        )}
      </div>
      <div className="overview__vitals">
        <VitalsPanel state={twin.state} />
      </div>
      <div className="overview__chart panel">
        {recorded ? <RecentChart /> : <LiveChart buffer={twin.buffer} metric="heart_rate" />}
      </div>
      <div className="overview__events">
        <EventFeed events={twin.events} limit={6} />
      </div>
    </div>
  );
}
