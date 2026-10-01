import { EventFeed } from "../components/EventFeed";
import { LiveChart } from "../components/LiveChart";
import { StatePanel } from "../components/StatePanel";
import { VitalsPanel } from "../components/VitalsPanel";
import { WellnessPanel } from "../components/WellnessPanel";
import type { LiveTwin } from "../hooks/useLiveTwin";
import { TwinScene } from "../twin3d/TwinScene";

export function Overview({ twin }: { twin: LiveTwin }) {
  return (
    <div className="overview">
      <div className="overview__state">
        <StatePanel state={twin.state} />
        <WellnessPanel state={twin.state} />
      </div>
      <div className="overview__twin">
        <TwinScene payload={twin.state} />
        <p className="twin-caption">
          Heart pulses at the live heart rate, lungs at the breathing rate, limbs move with measured activity, and the
          body lies down during sleep. Flagged vitals glow on their body region. Drag to rotate.
        </p>
      </div>
      <div className="overview__vitals">
        <VitalsPanel state={twin.state} />
      </div>
      <div className="overview__chart panel">
        <LiveChart buffer={twin.buffer} metric="heart_rate" />
      </div>
      <div className="overview__events">
        <EventFeed events={twin.events} limit={6} />
      </div>
    </div>
  );
}
