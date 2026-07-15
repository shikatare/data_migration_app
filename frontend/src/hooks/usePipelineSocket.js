import { useEffect, useRef, useState, useCallback } from "react";
import { io } from "socket.io-client";

export function usePipelineSocket() {
  const socketRef = useRef(null);
  const [events, setEvents] = useState([]);
  const [runComplete, setRunComplete] = useState(null);
  const [runSummary, setRunSummary] = useState(null);

  useEffect(() => {
    const socket = io("/", { path: "/socket.io" });
    socketRef.current = socket;

    socket.on("agent_event", (evt) => setEvents((prev) => [...prev, evt]));
    socket.on("run_complete", (record) => setRunComplete(record));
    socket.on("run_complete_summary", ({ summary }) => setRunSummary(summary));

    return () => socket.disconnect();
  }, []);

  const joinRun = useCallback((runId) => {
    setEvents([]);
    setRunComplete(null);
    setRunSummary(null);
    socketRef.current?.emit("join_run", runId);
  }, []);

  return { events, runComplete, runSummary, joinRun };
}
