import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { client, errorMessage } from "./client";

// Read-only slice: the Create/Update forms need the instructor list for the dropdown.
export const fetchInstructors = createAsyncThunk("instructors/fetch", async (_, { rejectWithValue }) => {
  try {
    const { data } = await client.get("/api/instructors", { params: { page: 1, page_size: 100 } });
    return data.items;
  } catch (err) {
    return rejectWithValue(errorMessage(err));
  }
});

const instructorsSlice = createSlice({
  name: "instructors",
  initialState: { items: [], status: "idle", error: null },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchInstructors.pending, (state) => {
        state.status = "loading";
      })
      .addCase(fetchInstructors.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload;
      })
      .addCase(fetchInstructors.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload || action.error.message;
      });
  },
});

export default instructorsSlice.reducer;
