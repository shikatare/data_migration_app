import express from "express";
import http from "http";
import cors from "cors";
import dotenv from "dotenv";
import { Server } from "socket.io";
import { pipelineRouter } from "./src/routes/pipeline.routes.js";

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json());

const server = http.createServer(app);
const io = new Server(server, { cors: { origin: "*" } });

io.on("connection", (socket) => {
  socket.on("join_run", (runId) => {
    socket.join(`run:${runId}`);
  });
});

app.use("/api/pipeline", pipelineRouter(io));

app.get("/api/health", (req, res) => res.json({ ok: true }));

const PORT = process.env.PORT || 4000;
server.listen(PORT, () => {
  console.log(`Migration Agent backend listening on :${PORT}`);
});