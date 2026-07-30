import { MeasurementClient } from "./MeasurementClient";

type MeasurementsPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function getParam(
  params: Record<string, string | string[] | undefined>,
  key: string,
  fallback: string,
) {
  const value = params[key];
  if (Array.isArray(value)) return value[0] ?? fallback;
  return value ?? fallback;
}

export default async function MeasurementsPage({ searchParams }: MeasurementsPageProps) {
  const params = searchParams ? await searchParams : {};
  return (
    <MeasurementClient
      initialDatasetId={getParam(params, "datasetId", "missing_struts")}
      requestedThreshold={getParam(params, "threshold", "Not provided")}
    />
  );
}
