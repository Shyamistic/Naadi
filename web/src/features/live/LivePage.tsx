import { useT } from "../../i18n/I18nProvider";export default function LivePage(){const {t}=useT();return <><h1>{t("live.title")}</h1><p>{t("live.privacy")}</p></>}
