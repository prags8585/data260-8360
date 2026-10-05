import { configureStore } from "@reduxjs/toolkit";
import coursesReducer from "./coursesSlice";
import instructorsReducer from "./instructorsSlice";

export const store = configureStore({
  reducer: {
    courses: coursesReducer,
    instructors: instructorsReducer,
  },
});
