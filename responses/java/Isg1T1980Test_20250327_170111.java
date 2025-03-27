package isg1t1980;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class Isg1T1980Test {

    private TestDataProvider dataProvider;
    private IntegrationLogService logService;
    private AppExtService appExtService;
    private PersonLimitService personLimitService;

    @BeforeEach
    public void setup() {
        dataProvider = new TestDataProvider();
        logService = new IntegrationLogService();
        appExtService = new AppExtService();
        personLimitService = new PersonLimitService();
    }

    @Test
    public void testCreateIsjPolicyWithLimits() throws Exception {
        // Шаг 1: Создание договора ИСЖ на сумму, близкую к лимиту
        int amount = 1000000000; // для УК
        int gkAmount = 80000000; // для ГК
        String policyId = dataProvider.createIsjPolicy(amount, gkAmount);

        // Шаг 2: Отправка запроса general на оформление любого продукта УК, ГК, Сберполиса
        int productType = 1; // УК
        String requestId = dataProvider.sendGeneralRequest(policyId, productType);

        // Шаг 3: Проверка наличия записи об отправке запроса по кумуляции
        boolean hasIntegrationLogRecord = logService.hasIntegrationLogRecord(requestId, "ISG_CUMULATION");
        assertTrue(hasIntegrationLogRecord);

        // Шаг 4: Проверка в таблице appext записи дополнительного параметра
        String additionalParameterValue = appExtService.getAdditionalParameterValue(policyId, "4440311");
        assertNotNull(additionalParameterValue);
        JSONObject jsonObject = new JSONObject(additionalParameterValue);
        assertEquals("", jsonObject.getString("error"));

        // Шаг 5: Проверка ответа от микросервиса в таблице appext
        int result = appExtService.getNumberValue(policyId, "4440568");
        assertEquals(1, result);

        // Шаг 6: Получение информации о лимитах по рискам НС
        long totalRiskSum = personLimitService.getTotalRiskSum(policyId);
        long currentPolicyRisk = appExtService.getNumberValue(policyId, "8857");

        // Шаг 7: Сравнение суммы рисков с лимитом
        long limitAmount = 1000000000; // лимит для УК
        if (totalRiskSum > limitAmount) {
            fail("Лимит превышен: общая сумма рисков превышает лимит.");
        } else {
            System.out.println("Все в порядке: лимит не превышен.");
        }

        // Шаг 8: Проверка ответа на general на наличие сообщения об андеррайтинге
        String generalResponse = dataProvider.getGeneralResponse(requestId);
        if (generalResponse != null && !generalResponse.isEmpty()) {
            JSONObject jsonObject2 = new JSONObject(generalResponse);
            assertEquals("По заявке предусмотрен андеррайтинг", jsonObject2.getString("StatusDesc"));
        } else {
            fail("Не удалось найти сообщение об андеррайтинге в ответе на general.");
        }
    }
}