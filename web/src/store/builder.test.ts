import { beforeEach, describe, expect, it } from "vitest";
import { blankDraft } from "../lib/draft";
import { useBuilder } from "./builder";

beforeEach(() => {
  localStorage.clear();
  useBuilder.setState({
    draft: blankDraft(6, 6),
    past: [],
    future: [],
    tool: "wall",
    selected: null,
    issues: [],
    library: [],
    stroking: false,
  });
});

describe("builder store", () => {
  it("records one undo step per drag, not per cell", () => {
    const b = useBuilder.getState();
    b.beginStroke();
    for (const c of [1, 2, 3, 4]) useBuilder.getState().paintAt([0, c]);
    expect(useBuilder.getState().draft.terrain[0]).toBe(".####.");
    expect(useBuilder.getState().past).toHaveLength(1);
    useBuilder.getState().undo();
    expect(useBuilder.getState().draft.terrain[0]).toBe("......");
    useBuilder.getState().redo();
    expect(useBuilder.getState().draft.terrain[0]).toBe(".####.");
  });

  it("a drag that changes nothing leaves no undo step", () => {
    const b = useBuilder.getState();
    b.beginStroke();
    useBuilder.getState().paintAt([0, 0]); // floor -> wall changes; do wall -> wall next
    useBuilder.getState().beginStroke();
    useBuilder.getState().paintAt([0, 0]);
    expect(useBuilder.getState().past).toHaveLength(1);
  });

  it("a new edit clears the redo stack", () => {
    const b = useBuilder.getState();
    b.beginStroke();
    b.paintAt([0, 0]);
    useBuilder.getState().undo();
    expect(useBuilder.getState().future).toHaveLength(1);
    useBuilder.getState().edit((d) => ({ ...d, name: "renamed" }));
    expect(useBuilder.getState().future).toHaveLength(0);
  });

  it("select mode picks a person instead of painting", () => {
    useBuilder.getState().setTool("select");
    useBuilder.getState().paintAt([5, 3]); // default person p1 sits bottom-middle of a 6x6
    expect(useBuilder.getState().selected).toBe("p1");
    expect(useBuilder.getState().draft.terrain[5]).toBe("......");
  });

  it("saves to and removes from the browser library", () => {
    useBuilder.getState().save();
    expect(useBuilder.getState().library.map((l) => l.name)).toEqual(["My scenario"]);
    expect(JSON.parse(localStorage.getItem("resq.scenarios") ?? "[]")).toHaveLength(1);
    useBuilder.getState().remove("My scenario");
    expect(useBuilder.getState().library).toEqual([]);
  });

  it("resizing is undoable", () => {
    useBuilder.getState().resize(8, 9);
    expect(useBuilder.getState().draft.grid_size).toEqual([8, 9]);
    useBuilder.getState().undo();
    expect(useBuilder.getState().draft.grid_size).toEqual([6, 6]);
  });
});
