import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { client, errorMessage } from "./client";

// --- async thunks: one per FastAPI endpoint -------------------------------

export const fetchCourses = createAsyncThunk("courses/fetch", async (_, { rejectWithValue }) => {
  try {
    const { data } = await client.get("/api/courses");
    return data;
  } catch (err) {
    return rejectWithValue(errorMessage(err));
  }
});

export const createCourse = createAsyncThunk("courses/create", async (course, { rejectWithValue }) => {
  try {
    const { data } = await client.post("/api/courses", course);
    return data;
  } catch (err) {
    return rejectWithValue(errorMessage(err));
  }
});

export const updateCourse = createAsyncThunk("courses/update", async ({ id, ...course }, { rejectWithValue }) => {
  try {
    const { data } = await client.put(`/api/courses/${id}`, course);
    return data;
  } catch (err) {
    return rejectWithValue(errorMessage(err));
  }
});

export const deleteCourse = createAsyncThunk("courses/delete", async (id, { rejectWithValue }) => {
  try {
    await client.delete(`/api/courses/${id}`);
    return id;
  } catch (err) {
    return rejectWithValue(errorMessage(err));
  }
});

// --- slice -------------------------------------------------------------------

const coursesSlice = createSlice({
  name: "courses",
  initialState: { items: [], status: "idle", error: null },
  reducers: {
    clearError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchCourses.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchCourses.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload;
      })
      .addCase(fetchCourses.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload || action.error.message;
      })
      .addCase(createCourse.fulfilled, (state, action) => {
        state.items.push(action.payload);
        state.error = null;
      })
      .addCase(updateCourse.fulfilled, (state, action) => {
        const i = state.items.findIndex((c) => c.id === action.payload.id);
        if (i !== -1) state.items[i] = action.payload;
        state.error = null;
      })
      .addCase(deleteCourse.fulfilled, (state, action) => {
        state.items = state.items.filter((c) => c.id !== action.payload);
        state.error = null;
      })
      .addMatcher(
        (action) => [createCourse.rejected.type, updateCourse.rejected.type, deleteCourse.rejected.type].includes(action.type),
        (state, action) => {
          state.error = action.payload || action.error.message;
        }
      );
  },
});

export const { clearError } = coursesSlice.actions;
export default coursesSlice.reducer;
