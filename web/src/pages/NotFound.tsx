import { Link } from "react-router-dom";
import { Button } from "@/components/ui";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center gap-4">
      <div className="text-6xl font-semibold text-fabric-gray-130">404</div>
      <div className="text-lg text-fabric-gray-160">
        That page is off the rate card.
      </div>
      <Link to="/">
        <Button variant="primary">Back to dashboard</Button>
      </Link>
    </div>
  );
}
