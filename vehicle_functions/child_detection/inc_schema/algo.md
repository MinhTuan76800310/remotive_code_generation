1. yaml.safe_load(ecu_path)  → spec["model"], spec["namespace_types"], spec["software_components"], spec["handlers"], spec["websocket_listeners"]
2. if spec["software_components"] is present and non-empty:
   2.1 for each path in software_components:
       - resolve path (absolute or relative to ECU file's directory)
       - file_not_found  → BuilderError "SWC file not found"
       - yaml.safe_load(swc_path) → swc_spec
       - if "model" in swc_spec  → BuilderError "SWC must not declare 'model:'"
       - if "namespace_types" in swc_spec  → BuilderError "SWC must not declare 'namespace_types:'"
       - swc_name = stem(swc_path)  (e.g., "seatECU_softwarecomponent")
       - swc_records.append({"name": swc_name, "path": swc_path, "spec": swc_spec})
   2.2 inline handlers + websocket_listeners from each SWC into the ECU spec
       - record source SWC on each handler via a new HandlerIR.source_swc: str = "" field
       - record source SWC on each WebsocketListenerIR.source_swc: str = ""
   2.3 uniqueness check across inlined handlers (by name)  → BuilderError on dupe
   2.4 uniqueness check across inlined websocket_listeners (by name)  → BuilderError on dupe
3. for every inlined handler.input: frame_filter is INFERRED from signal prefix
       - signal format: "Frame.Signal" (e.g., "SeatInput.SeatOccupied")
       - frame_filter = signal.split(".", 1)[0]   # everything before the first dot
       - signal.split(".", 1) must yield exactly 2 parts  → BuilderError on bare signal
       - this replaces any explicit frame_filter field (no longer accepted)
4. run existing build_ir(spec) on the merged spec  → BehavioralModelIR
   (existing 16 invariants + strict-required now check namespace_types from ECU; SWC refs must resolve to ECU map)
